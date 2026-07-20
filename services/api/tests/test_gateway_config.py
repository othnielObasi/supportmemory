from app.config import Settings
from app.services.mcp_gateway import MCPGatewayService


def test_gateway_timeout_seconds_is_configurable():
    settings = Settings(GATEWAY_TIMEOUT_SECONDS=12)
    assert settings.gateway_timeout_seconds == 12


def test_mcp_uses_generic_gateway_fields():
    settings = Settings(
        MCP_GATEWAY_URL="https://mcp.example.com",
        MCP_GATEWAY_API_KEY="generic-key",
    )
    service = MCPGatewayService(settings)
    assert service.enabled is True
    assert settings.effective_mcp_gateway_url == "https://mcp.example.com"
    assert service._endpoint("ticket_lookup") == "https://mcp.example.com/tools/ticket_lookup/invoke"


def test_mcp_falls_back_to_deterministic_local_when_unconfigured():
    settings = Settings(MCP_GATEWAY_URL=None, MCP_GATEWAY_API_KEY=None)
    service = MCPGatewayService(settings)
    assert service.enabled is False
    result = service._local_tool_result(tool_name="ticket_lookup", payload={"ticket_id": "TCK-1"})
    assert result.provider == "deterministic-local-tool"
    assert result.validation["passed"] is True
    assert result.observed_signals["next_page_token"] is None
