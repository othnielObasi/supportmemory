from app.config import Settings
from app.services.model_gateway import ModelGatewayRegistry
from app.services.alibaba_oss_service import AlibabaOSSService


def test_qwen_gateway_registered_and_disabled_without_key():
    settings = Settings(QWEN_API_KEY=None)
    registry = ModelGatewayRegistry(settings)
    assert registry.qwen.provider == "qwen"
    assert registry.qwen.enabled is False


def test_qwen_gateway_enabled_with_key_and_uses_dashscope_base_url():
    settings = Settings(QWEN_API_KEY="test-key", QWEN_MODEL="qwen-max")
    registry = ModelGatewayRegistry(settings)
    assert registry.qwen.enabled is True
    assert registry.qwen.configured_models["primary"] == "qwen-max"
    assert "dashscope" in settings.qwen_base_url


def test_default_gateway_prefers_qwen_when_configured():
    settings = Settings(QWEN_API_KEY="test-key", DEFAULT_MODEL_GATEWAY="qwen")
    registry = ModelGatewayRegistry(settings)
    gateway = registry.get()
    assert gateway is registry.qwen


def test_default_gateway_fails_closed_without_any_keys():
    settings = Settings(
        QWEN_API_KEY=None, OPENAI_API_KEY=None, OPENROUTER_API_KEY=None,
        GEMINI_API_KEY=None, DEFAULT_MODEL_GATEWAY="qwen",
    )
    registry = ModelGatewayRegistry(settings)
    gateway = registry.get()
    assert gateway.enabled is False
    assert gateway.configured_models["primary"] == "qwen-not-configured"


def test_alibaba_oss_disabled_without_credentials():
    settings = Settings(ALIBABA_ACCESS_KEY_ID=None, ALIBABA_ACCESS_KEY_SECRET=None, ALIBABA_OSS_BUCKET=None)
    oss = AlibabaOSSService(settings)
    assert oss.enabled is False
    assert oss.archive_receipt("task-1", "hash-1", {"foo": "bar"}) is None


def test_alibaba_oss_enabled_with_credentials():
    settings = Settings(
        ALIBABA_ACCESS_KEY_ID="ak", ALIBABA_ACCESS_KEY_SECRET="sk",
        ALIBABA_OSS_BUCKET="tracememory-receipts",
        ALIBABA_OSS_ENDPOINT="https://oss-ap-southeast-1.aliyuncs.com",
    )
    oss = AlibabaOSSService(settings)
    assert oss.enabled is True
