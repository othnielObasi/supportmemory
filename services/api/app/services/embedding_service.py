from __future__ import annotations

import hashlib
import math
from typing import List

import httpx
import numpy as np

from app.config import Settings


class EmbeddingService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def provider(self) -> str:
        configured = (self.settings.embedding_provider or "auto").lower()
        if configured == "auto":
            if self.settings.qwen_api_key:
                return "qwen"
            if self.settings.openai_api_key:
                return "openai"
            return "hash"
        return configured

    @property
    def uses_hash(self) -> bool:
        return self.provider == "hash"

    async def embed(self, text: str) -> List[float]:
        provider = self.provider
        if provider == "qwen" and self.settings.qwen_api_key:
            return await self._qwen_embed(text)
        if provider == "openai" and self.settings.openai_api_key:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=self.settings.openai_api_key)
            result = await client.embeddings.create(model=self.settings.openai_embedding_model, input=text)
            return result.data[0].embedding
        return self._hash_embed(text, self.settings.embedding_dimensions)

    async def _qwen_embed(self, text: str) -> List[float]:
        """DashScope OpenAI-compatible embeddings (text-embedding-v3 / v4)."""
        model = getattr(self.settings, "qwen_embedding_model", None) or "text-embedding-v3"
        base = (self.settings.qwen_base_url or "https://dashscope-intl.aliyuncs.com/compatible-mode/v1").rstrip("/")
        url = f"{base}/embeddings"
        payload = {
            "model": model,
            "input": text[:8000],
            "encoding_format": "float",
        }
        headers = {
            "Authorization": f"Bearer {self.settings.qwen_api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.settings.gateway_timeout_seconds) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
            embedding = (((data.get("data") or [{}])[0]).get("embedding")) or []
            if embedding:
                return embedding
        except Exception:
            # Fall back to hash so ingest/search never hard-fails offline
            pass
        return self._hash_embed(text, self.settings.embedding_dimensions)

    def _hash_embed(self, text: str, dimensions: int) -> List[float]:
        vec = np.zeros(dimensions, dtype=float)
        # Include unigrams + bigrams for slightly better lexical geometry
        tokens = [t.lower() for t in text.replace("_", " ").replace("-", " ").split() if t.strip()]
        grams = list(tokens)
        grams.extend(f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1))
        for token in grams:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "big") % dimensions
            sign = 1 if digest[4] % 2 == 0 else -1
            vec[idx] += sign * (1.0 + math.log1p(len(token)))
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.round(6).tolist()


def cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    denom = np.linalg.norm(va) * np.linalg.norm(vb)
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
