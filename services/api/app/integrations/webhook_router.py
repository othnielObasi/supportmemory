from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.db.postgres import PostgresStore
from app.enterprise_api import get_store
from app.integrations.vault import IntegrationCredentialVault
from app.integrations.webhooks import WebhookService, WebhookVerificationError

router = APIRouter(prefix="/webhooks", tags=["integration-webhooks"])


def webhook_service(store: PostgresStore = Depends(get_store), settings: Settings = Depends(get_settings)) -> WebhookService:
    return WebhookService(store, IntegrationCredentialVault(settings))


@router.post("/{provider}/{integration_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(provider: str, integration_id: str, request: Request, service: WebhookService = Depends(webhook_service)):
    raw_body = await request.body()
    try:
        event_id, duplicate, immediate = await service.receive(provider, integration_id, request.headers, raw_body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WebhookVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if immediate is not None:
        return immediate
    return {"accepted": True, "event_id": event_id, "duplicate": duplicate}
