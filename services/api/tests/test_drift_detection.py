import pytest
from app.services.drift_service import DriftService
from app.models.schemas import TaskContract


class _NoGateway:
    """Forces the deterministic fallback path (no live model)."""
    configured_models = {"primary": "local-deterministic-gateway"}
    async def chat(self, **kw):  # pragma: no cover - should not be called
        raise AssertionError("model should not be called in fallback test")


def _contract():
    return TaskContract(
        task_id="t1", agent_id="a1",
        original_goal="Fix the backend authentication bug",
        approved_scope="backend auth module, login flow, token validation",
        forbidden_actions=["deploy to production", "modify billing"],
    )


@pytest.mark.asyncio
async def test_aligned_action_passes():
    svc = DriftService(store=None, gateway=_NoGateway())
    r = await svc.check(_contract(), "Inspect the token validation function in the auth module")
    assert r["aligned"] is True
    assert r["severity"] == "none"
    assert r["derivation"] == "deterministic_fallback"


@pytest.mark.asyncio
async def test_drifted_action_flagged():
    svc = DriftService(store=None, gateway=_NoGateway())
    r = await svc.check(_contract(), "Redesign the marketing landing page and add onboarding copy")
    assert r["aligned"] is False
    assert r["severity"] == "major"


@pytest.mark.asyncio
async def test_forbidden_action_flagged():
    svc = DriftService(store=None, gateway=_NoGateway())
    r = await svc.check(_contract(), "Deploy to production immediately")
    assert r["aligned"] is False
    assert "forbidden" in r["reason"].lower()
