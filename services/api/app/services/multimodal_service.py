from __future__ import annotations

import re
from typing import Any, List, Optional

from app.config import Settings
from app.models.schemas import (
    KbIngestRequest,
    MultimodalAnalyzeRequest,
    MultimodalAnalyzeResponse,
    MultimodalAttachment,
    new_id,
)
from app.services.kb_ingest_service import KbIngestService


class MultimodalService:
    """Multimodal SupportMemory path: image (Qwen-VL) + text memory + optional voice elsewhere.

    Keyless demos use a deterministic vision fallback so judges can still see the
    multimodal memory lifecycle without DashScope credentials.
    """

    def __init__(self, settings: Settings, gateway: Any, kb: Optional[KbIngestService] = None):
        self.settings = settings
        self.gateway = gateway
        self.kb = kb

    async def analyze(self, payload: MultimodalAnalyzeRequest) -> MultimodalAnalyzeResponse:
        attachment = payload.attachment
        if attachment.type != "image":
            # Audio/document: store caption/text path; voice TTS lives on /voice/run-summary.
            summary = attachment.caption or (
                f"{attachment.type.title()} attachment accepted "
                f"({attachment.filename or attachment.mime_type}). "
                "Transcribe/extract offline or via provider, then ingest text into KB."
            )
            signals = self._extract_signals(summary)
            context_prefix = self._context_prefix(summary, signals, attachment.type)
            kb_document_id = await self._maybe_ingest(payload, summary)
            return MultimodalAnalyzeResponse(
                analysis_id=new_id("mm"),
                modality=attachment.type,
                provider="supportmemory-multimodal",
                model="passthrough",
                used_fallback=True,
                summary=summary,
                extracted_signals=signals,
                context_prefix=context_prefix,
                kb_document_id=kb_document_id,
                note="Non-image modalities are accepted and remembered as text evidence in this build.",
            )

        summary, provider, model, used_fallback = await self._analyze_image(payload.prompt, attachment)
        signals = self._extract_signals(summary)
        context_prefix = self._context_prefix(summary, signals, "image")
        kb_document_id = await self._maybe_ingest(payload, summary)
        return MultimodalAnalyzeResponse(
            analysis_id=new_id("mm"),
            modality="image",
            provider=provider,
            model=model,
            used_fallback=used_fallback,
            summary=summary,
            extracted_signals=signals,
            context_prefix=context_prefix,
            kb_document_id=kb_document_id,
            note=(
                "Live Qwen-VL analysis"
                if not used_fallback
                else "Deterministic vision fallback (set QWEN_API_KEY for Qwen-VL)."
            ),
        )

    async def analyze_attachments(
        self,
        attachments: List[MultimodalAttachment],
        *,
        task_description: str,
        agent_id: str,
        ingest_to_kb: bool = False,
    ) -> tuple[str, List[dict]]:
        if not attachments:
            return "", []
        sections: list[str] = []
        records: list[dict] = []
        for attachment in attachments[:5]:
            result = await self.analyze(
                MultimodalAnalyzeRequest(
                    prompt=(
                        "You are SupportMemory vision. Describe this customer-support evidence. "
                        f"Task context: {task_description}"
                    ),
                    attachment=attachment,
                    agent_id=agent_id,
                    ingest_to_kb=ingest_to_kb,
                    title=attachment.filename or attachment.caption or "Support screenshot",
                )
            )
            sections.append(result.context_prefix)
            records.append(result.model_dump())
        return "\n\n".join(s for s in sections if s), records

    async def _analyze_image(
        self, prompt: str, attachment: MultimodalAttachment
    ) -> tuple[str, str, str, bool]:
        image_url = self._image_ref(attachment)
        vision_model = getattr(self.settings, "qwen_vl_model", "qwen-vl-max")
        chat = getattr(self.gateway, "chat", None)
        provider_name = getattr(self.gateway, "provider", "") or ""
        # Live vision only when a real cloud gateway is selected (Qwen-VL / OpenAI-compatible).
        if (
            callable(chat)
            and getattr(self.gateway, "enabled", False)
            and image_url
            and provider_name in {"qwen", "openai", "openrouter"}
        ):
            result = await chat(
                system=(
                    "You are the vision component of SupportMemory, a multimodal customer-support agent. "
                    "Extract visible errors, UI labels, payment/processor messages, and likely next actions. "
                    "Be concise and factual."
                ),
                user=prompt,
                images=[image_url],
                model=vision_model if provider_name == "qwen" else None,
                max_tokens=500,
                temperature=0,
            )
            content = (getattr(result, "content", None) or "").strip()
            if content:
                return (
                    content,
                    getattr(result, "provider", provider_name),
                    getattr(result, "model", vision_model),
                    bool(getattr(result, "used_fallback", False)),
                )

        return self._fallback_image_summary(attachment, prompt), "local-vision-fallback", "deterministic-vision", True

    def _image_ref(self, attachment: MultimodalAttachment) -> Optional[str]:
        if attachment.url:
            return attachment.url
        if attachment.data_base64:
            mime = attachment.mime_type or "image/png"
            raw = attachment.data_base64
            if raw.startswith("data:"):
                return raw
            return f"data:{mime};base64,{raw}"
        return None

    def _fallback_image_summary(self, attachment: MultimodalAttachment, prompt: str) -> str:
        caption = attachment.caption or attachment.filename or "support screenshot"
        lower = f"{caption} {prompt}".lower()
        if any(token in lower for token in ("payment", "refund", "card", "billing", "charge")):
            focus = (
                "Visible payment/billing UI. Likely processor decline or duplicate charge. "
                "Prefer confirming ticket ID and processor reference before refund approval."
            )
        elif any(token in lower for token in ("login", "password", "auth", "2fa")):
            focus = (
                "Visible authentication error. Likely session/login failure. "
                "Do not ask the customer to re-enter secrets already captured in prior tickets."
            )
        else:
            focus = (
                "Visible product/UI error evidence attached to the support case. "
                "Preserve screenshot findings in memory and avoid restarting diagnosis from zero."
            )
        return (
            f"Vision fallback summary for '{caption}': {focus} "
            "Multimodal memory recorded so the next session can recall this evidence."
        )

    def _extract_signals(self, summary: str) -> List[str]:
        signals: list[str] = []
        lowered = summary.lower()
        for token in ("refund", "payment", "login", "timeout", "403", "500", "duplicate", "pagination", "compliance"):
            if token in lowered:
                signals.append(token)
        # Capture simple ERROR-looking tokens
        signals.extend(re.findall(r"\b[A-Z]{3,}[_-][A-Z0-9_]+\b", summary)[:5])
        # de-dupe preserve order
        seen = set()
        ordered = []
        for signal in signals:
            if signal not in seen:
                seen.add(signal)
                ordered.append(signal)
        return ordered[:8]

    def _context_prefix(self, summary: str, signals: List[str], modality: str) -> str:
        signal_line = ", ".join(signals) if signals else "none"
        return (
            f"Relevant multimodal evidence ({modality}):\n"
            f"- {summary[:600]}\n"
            f"- Extracted signals: {signal_line}\n\n"
            "Use this visual/audio evidence with ticket history; do not ignore attached proof."
        )

    async def _maybe_ingest(self, payload: MultimodalAnalyzeRequest, summary: str) -> Optional[str]:
        if not payload.ingest_to_kb or self.kb is None:
            return None
        title = payload.title or payload.attachment.filename or payload.attachment.caption or "Multimodal support evidence"
        ingested = await self.kb.ingest(
            KbIngestRequest(
                title=title,
                text=summary,
                source_type="multimodal",
                source_system="qwen_vl" if not summary.startswith("Vision fallback") else "vision_fallback",
                tags=["multimodal", payload.attachment.type, "supportmemory"],
                agent_id=payload.agent_id,
            )
        )
        return ingested.document_id
