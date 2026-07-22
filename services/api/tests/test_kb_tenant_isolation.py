from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import get_services, router
from app.enterprise_api import principal_dependency
from app.security import EnterprisePrincipal


class RecordingKb:
    def __init__(self):
        self.calls = []

    async def list_documents(self, **kwargs):
        self.calls.append(("list", kwargs))
        return []

    async def search(self, query, **kwargs):
        self.calls.append(("search", {"query": query, **kwargs}))
        return []


def _client():
    kb = RecordingKb()
    principal = EnterprisePrincipal(
        organisation_id="org_authorised",
        workspace_id="wrk_authorised",
        project_id="prj_authorised",
        environment_id="prod",
        actor_id="operator_1",
        role="operator",
        scopes={"memory:read", "memory:approve"},
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[principal_dependency] = lambda: principal
    app.dependency_overrides[get_services] = lambda: {"kb": kb, "retrieval": type("Retrieval", (), {"context_builder": type("Builder", (), {"build": lambda self, rules, kb_hits: ""})()})()}
    return TestClient(app), kb


def test_kb_document_list_uses_authenticated_tenant_not_query_parameters():
    client, kb = _client()
    response = client.get("/api/kb/documents?organisation_id=org_attacker&workspace_id=wrk_attacker")
    assert response.status_code == 200
    assert kb.calls == [("list", {"limit": 50, "organisation_id": "org_authorised", "workspace_id": "wrk_authorised"})]


def test_kb_search_uses_authenticated_tenant_not_payload_scope():
    client, kb = _client()
    response = client.post("/api/kb/search", json={"query": "refund policy", "organisation_id": "org_attacker", "workspace_id": "wrk_attacker"})
    assert response.status_code == 200
    call = kb.calls[0]
    assert call[0] == "search"
    assert call[1]["organisation_id"] == "org_authorised"
    assert call[1]["workspace_id"] == "wrk_authorised"


def test_kb_read_requires_memory_scope():
    client, _ = _client()
    client.app.dependency_overrides[principal_dependency] = lambda: EnterprisePrincipal(
        organisation_id="org_authorised", workspace_id="wrk_authorised", project_id="prj_authorised",
        environment_id="prod", actor_id="viewer_1", role="viewer", scopes=set(),
    )
    response = client.get("/api/kb/documents")
    assert response.status_code == 403
