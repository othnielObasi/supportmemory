from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import Settings, get_settings
from app.db.postgres import PostgresStore
from app.enterprise_api import get_store, principal_dependency
from app.integrations.oauth import OAuthService
from app.integrations.schemas import OAuthStartRequest, OAuthStartResponse
from app.integrations.service import IntegrationService
from app.integrations.vault import IntegrationCredentialVault
from app.security import EnterprisePrincipal

router = APIRouter(prefix="/integrations/oauth", tags=["integration-oauth"])


def oauth_service(store: PostgresStore = Depends(get_store), settings: Settings = Depends(get_settings)) -> OAuthService:
    return OAuthService(store, settings, IntegrationService(store, IntegrationCredentialVault(settings)))


@router.post("/start", response_model=OAuthStartResponse)
async def start_oauth(payload: OAuthStartRequest, principal: EnterprisePrincipal = Depends(principal_dependency), service: OAuthService = Depends(oauth_service)):
    principal.require(["integrations:write"])
    try:
        return await service.start(payload, principal)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/callback/{provider}")
async def oauth_callback(provider: str, state: str = Query(min_length=20), code: str = Query(min_length=1), service: OAuthService = Depends(oauth_service), settings: Settings = Depends(get_settings)):
    if provider not in {"zendesk", "intercom", "slack"}:
        raise HTTPException(status_code=404, detail="Unsupported OAuth provider")
    try:
        integration_id = await service.callback(provider, state, code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"{settings.public_console_url.rstrip('/')}/integrations.html?connected={integration_id}", status_code=303)
