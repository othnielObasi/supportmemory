"""Mock compliance ticket tool used after task modification."""

def fetch_compliance_tickets() -> dict:
    return {"blockers": ["vendor documentation gap", "review handoff delay"], "requires_human_review": False}
