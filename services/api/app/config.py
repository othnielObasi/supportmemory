from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='SupportMemory', alias='APP_NAME')
    environment: str = Field(default='development', alias='ENVIRONMENT')
    api_prefix: str = Field(default='/api', alias='API_PREFIX')
    frontend_origin: str = Field(default='http://localhost:5173', alias='FRONTEND_ORIGIN')
    database_url: str = Field(default='postgresql://tracememory:tracememory@localhost:5432/tracememory_dev', alias='DATABASE_URL')
    database_pool_min_size: int = Field(default=1, alias='DATABASE_POOL_MIN_SIZE')
    database_pool_max_size: int = Field(default=10, alias='DATABASE_POOL_MAX_SIZE')
    database_command_timeout_seconds: int = Field(default=30, alias='DATABASE_COMMAND_TIMEOUT_SECONDS')
    signing_secret: str = Field(default='replace-with-a-secure-secret', alias='SIGNING_SECRET')
    receipt_signing_key_b64: str | None = Field(default=None, alias='RECEIPT_SIGNING_KEY_B64')
    runtime_governor_mode: str = Field(default='local', alias='RUNTIME_GOVERNOR_MODE')
    # hybrid = redact on reads/internal; strict on external (recommended for SupportMemory)
    # Also: redact | block | require_approval
    runtime_governor_pii_mode: str = Field(default='hybrid', alias='RUNTIME_GOVERNOR_PII_MODE')
    # When pii_mode=hybrid: block | require_approval for send_*/refund_* etc.
    runtime_governor_external_pii_mode: str = Field(default='require_approval', alias='RUNTIME_GOVERNOR_EXTERNAL_PII_MODE')
    runtime_governor_block_unknown_tools: bool = Field(default=False, alias='RUNTIME_GOVERNOR_BLOCK_UNKNOWN_TOOLS')
    runtime_governor_tool_allowlist: str = Field(default='', alias='RUNTIME_GOVERNOR_TOOL_ALLOWLIST')
    # auto = Qwen embeddings when QWEN_API_KEY set, else OpenAI, else hash
    embedding_provider: str = Field(default='auto', alias='EMBEDDING_PROVIDER')
    embedding_dimensions: int = Field(default=384, alias='EMBEDDING_DIMENSIONS')
    qwen_embedding_model: str = Field(default='text-embedding-v3', alias='QWEN_EMBEDDING_MODEL')
    openai_api_key: str | None = Field(default=None, alias='OPENAI_API_KEY')
    openai_embedding_model: str = Field(default='text-embedding-3-small', alias='OPENAI_EMBEDDING_MODEL')
    openai_chat_model: str = Field(default='gpt-4.1-mini', alias='OPENAI_CHAT_MODEL')
    anthropic_api_key: str | None = Field(default=None, alias='ANTHROPIC_API_KEY')
    anthropic_model: str = Field(default='claude-3-5-sonnet-latest', alias='ANTHROPIC_MODEL')
    gemini_api_key: str | None = Field(default=None, alias='GEMINI_API_KEY')
    gemini_model: str = Field(default='gemini-2.5-flash', alias='GEMINI_MODEL')
    openrouter_api_key: str | None = Field(default=None, alias='OPENROUTER_API_KEY')
    openrouter_model: str = Field(default='openai/gpt-4.1-mini', alias='OPENROUTER_MODEL')
    qwen_api_key: str | None = Field(default=None, alias='QWEN_API_KEY')
    qwen_model: str = Field(default='qwen-max', alias='QWEN_MODEL')
    qwen_vl_model: str = Field(default='qwen-vl-max', alias='QWEN_VL_MODEL')
    qwen_base_url: str = Field(default='https://dashscope-intl.aliyuncs.com/compatible-mode/v1', alias='QWEN_BASE_URL')
    qwen_dashscope_api_base: str | None = Field(default=None, alias='QWEN_DASHSCOPE_API_BASE')
    qwen_tts_model: str = Field(default='qwen3-tts-flash', alias='QWEN_TTS_MODEL')
    qwen_tts_voice: str = Field(default='Cherry', alias='QWEN_TTS_VOICE')
    qwen_tts_language: str = Field(default='Auto', alias='QWEN_TTS_LANGUAGE')
    qwen_asr_model: str = Field(default='qwen3-asr-flash', alias='QWEN_ASR_MODEL')
    alibaba_access_key_id: str | None = Field(default=None, alias='ALIBABA_ACCESS_KEY_ID')
    alibaba_access_key_secret: str | None = Field(default=None, alias='ALIBABA_ACCESS_KEY_SECRET')
    alibaba_oss_region: str = Field(default='oss-ap-southeast-1', alias='ALIBABA_OSS_REGION')
    alibaba_oss_endpoint: str = Field(default='https://oss-ap-southeast-1.aliyuncs.com', alias='ALIBABA_OSS_ENDPOINT')
    alibaba_oss_bucket: str | None = Field(default=None, alias='ALIBABA_OSS_BUCKET')
    ollama_base_url: str = Field(default='http://localhost:11434', alias='OLLAMA_BASE_URL')
    ollama_model: str = Field(default='llama3.1', alias='OLLAMA_MODEL')
    fireworks_api_key: str | None = Field(default=None, alias='FIREWORKS_API_KEY')
    fireworks_model: str = Field(default='accounts/fireworks/models/llama-v3p1-70b-instruct', alias='FIREWORKS_MODEL')
    fireworks_base_url: str = Field(default='https://api.fireworks.ai/inference/v1', alias='FIREWORKS_BASE_URL')
    gateway_timeout_seconds: int = Field(default=45, alias='GATEWAY_TIMEOUT_SECONDS')
    # Provider-agnostic MCP/tool gateway.
    # through aliases in code, but TraceMemory should depend on these generic names.
    mcp_gateway_url: str | None = Field(default=None, alias='MCP_GATEWAY_URL')
    mcp_gateway_api_key: str | None = Field(default=None, alias='MCP_GATEWAY_API_KEY')
    mcp_tool_invoke_path: str = Field(default='/tools/{tool_name}/invoke', alias='MCP_TOOL_INVOKE_PATH')
    aws_region: str | None = Field(default=None, alias='AWS_REGION')
    aws_runtime: str | None = Field(default=None, alias='AWS_RUNTIME')
    deployment_id: str | None = Field(default=None, alias='DEPLOYMENT_ID')


    # Google/Gemini reference integration
    google_gemini_api_key: str | None = Field(default=None, alias='GOOGLE_GEMINI_API_KEY')
    google_vertex_project: str | None = Field(default=None, alias='GOOGLE_VERTEX_PROJECT')
    google_vertex_location: str = Field(default='us-central1', alias='GOOGLE_VERTEX_LOCATION')
    google_gemini_model: str = Field(default='gemini-2.5-pro', alias='GOOGLE_GEMINI_MODEL')
    google_gemini_fallback_model: str = Field(default='gemini-2.5-flash', alias='GOOGLE_GEMINI_FALLBACK_MODEL')
    google_embedding_model: str = Field(default='text-embedding-004', alias='GOOGLE_EMBEDDING_MODEL')
    google_agent_engine_runtime: str | None = Field(default=None, alias='GOOGLE_AGENT_ENGINE_RUNTIME')

    # Enterprise adoption controls
    auth_required: bool = Field(default=False, alias='AUTH_REQUIRED')
    default_organisation_id: str = Field(default='org_default', alias='DEFAULT_ORGANISATION_ID')
    default_workspace_id: str = Field(default='wrk_default', alias='DEFAULT_WORKSPACE_ID')
    default_project_id: str = Field(default='prj_default', alias='DEFAULT_PROJECT_ID')
    default_environment_id: str = Field(default='dev', alias='DEFAULT_ENVIRONMENT_ID')
    bootstrap_admin_token: str | None = Field(default=None, alias='BOOTSTRAP_ADMIN_TOKEN')
    default_model_gateway: str = Field(default='openai', alias='DEFAULT_MODEL_GATEWAY')
    audit_log_retention_days: int = Field(default=365, alias='AUDIT_LOG_RETENTION_DAYS')
    run_retention_days: int = Field(default=365, alias='RUN_RETENTION_DAYS')
    enable_open_telemetry: bool = Field(default=False, alias='ENABLE_OPEN_TELEMETRY')
    otel_service_name: str = Field(default='tracememory-api', alias='OTEL_SERVICE_NAME')
    worker_poll_interval_seconds: int = Field(default=5, alias='WORKER_POLL_INTERVAL_SECONDS')
    worker_lease_seconds: int = Field(default=300, alias='WORKER_LEASE_SECONDS')

    @property
    def cors_origins(self) -> List[str]:
        return list({self.frontend_origin, 'http://localhost:3000', 'http://localhost:5173'})

    @property
    def aws_ready(self) -> bool:
        return bool(self.openai_api_key or self.openrouter_api_key)

    @property
    def effective_mcp_gateway_url(self) -> str | None:
        return self.mcp_gateway_url

    @property
    def effective_mcp_gateway_api_key(self) -> str | None:
        return self.mcp_gateway_api_key

    @property
    def effective_mcp_tool_invoke_path(self) -> str:
        return self.mcp_tool_invoke_path

    @property
    def mcp_ready(self) -> bool:
        return bool(self.effective_mcp_gateway_url and self.effective_mcp_gateway_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
