from app.context_health.schemas import ContextBuildRequest, ContextCandidate
from app.context_health.service import ContextHealthService


def test_context_health_excludes_stale_and_includes_current():
    service = ContextHealthService()
    response, receipt = service.build_context(
        ContextBuildRequest(
            task="Investigate refund issue",
            candidate_context=[
                ContextCandidate(source_ref="old-policy", content="Old rule", relevance_score=90, freshness_score=10, trust_score=80, token_estimate=50),
                ContextCandidate(source_ref="current-policy", content="Current rule", relevance_score=90, freshness_score=90, trust_score=80, token_estimate=50),
            ],
        )
    )
    assert response.receipt_id == receipt.receipt_id
    assert "Current rule" in response.clean_context
    assert "Old rule" not in response.clean_context
    assert any(d.policy_id == "ctx-stale-block-v1" for d in response.decisions)
