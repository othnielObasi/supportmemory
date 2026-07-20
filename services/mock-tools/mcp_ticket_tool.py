"""Mock MCP-style ticket tool for the TraceMemory hackathon demo."""

def fetch_support_tickets(page_token: str | None = None) -> dict:
    if page_token == "page_2":
        return {"tickets": [{"id": "T-003", "issue": "compliance handoff delay"}], "next_page_token": None}
    return {"tickets": [{"id": "T-001", "issue": "missing evidence"}, {"id": "T-002", "issue": "delayed approval"}], "next_page_token": "page_2"}
