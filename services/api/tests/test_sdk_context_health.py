import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "packages" / "sdk-python"))

from tracememory import TraceMemoryClient


class CapturingClient(TraceMemoryClient):
    def __init__(self):
        super().__init__(base_url="http://testserver")
        self.calls = []

    def _request(self, method, path, payload=None):  # noqa: ANN001
        self.calls.append((method, path, payload))
        return {"ok": True, "path": path, "payload": payload}


def test_python_sdk_build_context_posts_expected_payload():
    client = CapturingClient()
    response = client.build_context(
        task="Investigate customer issue",
        candidate_context=[{"source_ref": "policy-v3", "content": "Current policy", "relevance_score": 90}],
        agent_type="openclaw_agent",
        token_budget=5000,
    )
    method, path, payload = client.calls[-1]
    assert response["ok"] is True
    assert method == "POST"
    assert path == "/api/context-health/build"
    assert payload["task"] == "Investigate customer issue"
    assert payload["agent_type"] == "openclaw_agent"
    assert payload["token_budget"] == 5000
    assert payload["candidate_context"][0]["source_ref"] == "policy-v3"


def test_python_sdk_get_context_receipts_uses_context_route():
    client = CapturingClient()
    client.get_context_receipts()
    method, path, payload = client.calls[-1]
    assert method == "GET"
    assert path == "/api/context-health/receipts"
    assert payload is None
