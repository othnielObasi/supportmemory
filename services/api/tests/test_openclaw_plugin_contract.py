from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "packages/openclaw-plugin-tracememory"


def test_openclaw_plugin_package_exists():
    assert (PLUGIN / "package.json").exists()
    assert (PLUGIN / "openclaw.plugin.json").exists()
    assert (PLUGIN / "src/client.ts").exists()
    assert (PLUGIN / "src/index.ts").exists()


def test_openclaw_plugin_uses_tracememory_api_prefix_and_context_health():
    client_ts = (PLUGIN / "src/client.ts").read_text()
    assert "apiPrefix" in client_ts
    assert "base.endsWith(prefix)" in client_ts
    assert "/context-health/build" in client_ts
    assert "/tool-traces" in client_ts


def test_openclaw_tool_trace_payload_matches_backend_contract():
    client_ts = (PLUGIN / "src/client.ts").read_text()
    assert "tool: input.toolName" in client_ts
    assert "tool_type: input.toolType" in client_ts
    assert "input: input.toolInput" in client_ts
    assert "output: input.toolOutput" in client_ts
    assert "observed_signals" in client_ts
    assert "tool_name:" not in client_ts
    assert "input_hash:" not in client_ts
