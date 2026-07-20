"""Mock policy-context tool that returns one fresh and one stale source."""

def fetch_policy_context() -> dict:
    return {"fresh": [{"id": "P-2026", "status": "active", "topic": "refund evidence"}], "stale": [{"id": "P-2023", "status": "expired", "topic": "old escalation rule"}]}
