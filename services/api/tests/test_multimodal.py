import pytest
from types import SimpleNamespace

from app.config import Settings
from app.models.schemas import MultimodalAnalyzeRequest, MultimodalAttachment
from app.services.embedding_service import EmbeddingService
from app.services.kb_ingest_service import KbIngestService
from app.services.model_gateway import ModelGatewayRegistry
from app.services.multimodal_service import MultimodalService


class MemoryStore:
    def __init__(self):
        self.data = {}

    async def insert_one(self, collection, doc):
        self.data.setdefault(collection, []).append(doc)
        return doc

    async def find_many(self, collection, query=None, limit=50, sort=None):
        rows = list(self.data.get(collection, []))
        query = query or {}
        return [row for row in rows if all(str(row.get(k)) == str(v) for k, v in query.items())][:limit]


class LiveVisionTestGateway:
    enabled = True
    provider = "qwen"

    async def chat(self, **kwargs):
        return SimpleNamespace(
            content="The screenshot contains a login error banner.",
            provider="qwen",
            model="qwen-vl-max",
            used_fallback=False,
        )


@pytest.mark.asyncio
async def test_multimodal_image_requires_live_provider():
    settings = Settings(QWEN_API_KEY=None, DEFAULT_MODEL_GATEWAY="qwen", embedding_provider="hash")
    gateway = ModelGatewayRegistry(settings).get()
    service = MultimodalService(settings, gateway)
    with pytest.raises(RuntimeError, match="Live vision provider"):
        await service.analyze(
            MultimodalAnalyzeRequest(
                prompt="Investigate this payment failure screenshot",
                attachment=MultimodalAttachment(
                    type="image",
                    caption="payment decline screenshot",
                    mime_type="image/png",
                ),
                ingest_to_kb=False,
            )
        )


@pytest.mark.asyncio
async def test_multimodal_can_ingest_vision_summary_to_kb():
    settings = Settings(QWEN_API_KEY=None, embedding_provider="hash", embedding_dimensions=64)
    store = MemoryStore()
    kb = KbIngestService(store, EmbeddingService(settings), settings)
    service = MultimodalService(settings, LiveVisionTestGateway(), kb=kb)
    result = await service.analyze(
        MultimodalAnalyzeRequest(
            prompt="Describe login error",
            attachment=MultimodalAttachment(
                type="image",
                caption="login failure UI",
                filename="login.png",
                data_base64="aW1hZ2U=",
            ),
            ingest_to_kb=True,
            title="Login screenshot memory",
        )
    )
    assert result.kb_document_id
    assert store.data.get("kb_documents")
    assert store.data.get("kb_chunks")


def test_qwen_descriptor_advertises_multimodal_vision():
    settings = Settings(QWEN_API_KEY="k", QWEN_VL_MODEL="qwen-vl-max")
    descriptors = ModelGatewayRegistry(settings).descriptors()
    qwen = next(item for item in descriptors if item.name == "qwen")
    assert "vision" in qwen.capabilities
    assert "multimodal" in qwen.capabilities
    assert qwen.models["vision"] == "qwen-vl-max"
