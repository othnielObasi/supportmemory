from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.schemas import HelpdeskMockTicketRequest, HelpdeskMockTicketResponse
from app.tools.ticket_tools import fetch_tickets


def fetch_helpdesk_mock(payload: HelpdeskMockTicketRequest) -> HelpdeskMockTicketResponse:
    """Return a Zendesk/Freshdesk-shaped payload from the mock ticket source.

    Live connectors would hit the vendor API/webhook; this preserves the contract
    for SupportMemory demos without requiring external credentials.
    """
    page = fetch_tickets(dataset_type=payload.dataset_type, page_token=payload.page_token)
    items: List[Dict[str, Any]] = list(page.get("items") or [])
    primary = items[0] if items else {"id": payload.ticket_id or "TCK-DEMO", "subject": "No tickets in page"}
    ticket_id = payload.ticket_id or str(primary.get("id") or primary.get("ticket_id") or "TCK-DEMO")

    comments: List[Dict[str, Any]] = []
    for idx, item in enumerate(items[:5]):
        body = item.get("issue") or item.get("summary") or item.get("description") or str(item)
        comments.append(
            {
                "id": f"cmt_{idx + 1}",
                "ticket_id": ticket_id,
                "author": item.get("requester") or item.get("customer") or "customer",
                "body": body,
                "public": True,
            }
        )

    subject_issue = primary.get("issue") or primary.get("subject") or primary.get("title") or f"Support ticket {ticket_id}"
    ticket = {
        "id": ticket_id,
        "subject": subject_issue,
        "status": primary.get("status") or "open",
        "priority": primary.get("severity") or primary.get("priority") or "normal",
        "tags": primary.get("tags") or ["supportmemory", payload.source_system],
        "custom_fields": {
            "dataset_type": payload.dataset_type,
            "records_in_page": len(items),
        },
        "raw_items_preview": items[:3],
    }

    return HelpdeskMockTicketResponse(
        source_system=payload.source_system,
        ticket=ticket,
        comments=comments,
        next_page_token=page.get("next_page_token"),
    )
