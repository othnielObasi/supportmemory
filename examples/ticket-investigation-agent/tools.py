SUPPORT_TICKETS = [{"id": "sup_001", "topic": "billing delay"}, {"id": "sup_002", "topic": "login failure"}]
COMPLIANCE_TICKETS = [{"id": "comp_001", "topic": "missing evidence"}, {"id": "comp_002", "topic": "delayed approval"}]

def fetch_tickets(dataset_type: str) -> list[dict]:
    return COMPLIANCE_TICKETS if dataset_type == "compliance_tickets" else SUPPORT_TICKETS
