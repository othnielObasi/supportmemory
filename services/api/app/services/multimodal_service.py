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
    """Analyze image evidence with a configured live vision provider."""

    def __init__(self, settings: Settings, gateway: Any, kb: Optional[KbIngestService] = None):
        self.settings = settings
        self.gateway = gateway
        self.kb = kb

    async def analyze(self, payload: MultimodalAnalyzeRequest) -> MultimodalAnalyzeResponse:
        attachment = payload.attachment
        if attachment.type != "image":
            raise RuntimeError(f"Live analysis for {attachment.type} attachments is not configured")

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
            note="Live vision-provider analysis",
        )

    async def analyze_attachments(
        self,
        attachments: List[MultimodalAttachment],
        *,
        task_description: str,
        agent_id: str,
        ingest_to_kb: bool = False,
        organisation_id: str = "org_default",
        workspace_id: str = "wrk_default",
        project_id: str = "prj_default",
        environment_id: str = "dev",
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
                    organisation_id=organisation_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    environment_id=environment_id,
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

        raise RuntimeError("Live vision provider is not configured or no image payload was supplied")

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
                source_system="vision_provider",
                tags=["multimodal", payload.attachment.type, "supportmemory"],
                agent_id=payload.agent_id,
                organisation_id=payload.organisation_id,
                workspace_id=payload.workspace_id,
                project_id=payload.project_id,
                environment_id=payload.environment_id,
            )
        )
        return ingested.document_id
