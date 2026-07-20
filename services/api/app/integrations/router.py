from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.config import Settings, get_settings
from app.db.postgres import PostgresStore
from app.enterprise_api import get_store, principal_dependency
from app.integrations.schemas import DeliveryCreateRequest, DeliveryResponse, IntegrationCreateRequest, IntegrationResponse, IntegrationTestResponse, IntegrationUpdateRequest
from app.integrations.service import IntegrationService
from app.integrations.vault import IntegrationCredentialVault
from app.security import EnterprisePrincipal

router = APIRouter(prefix="/integrations", tags=["integrations"])


def service_dependency(store: PostgresStore = Depends(get_store), settings: Settings = Depends(get_settings)) -> IntegrationService:
    return IntegrationService(store, IntegrationCredentialVault(settings))


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(principal: EnterprisePrincipal = Depends(principal_dependency), service: IntegrationService = Depends(service_dependency)):
    principal.require(["integrations:read"])
    return await service.list(principal)


@router.post("", response_model=IntegrationResponse, status_code=status.HTTP_201_CREATED)
async def create_integration(payload: IntegrationCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), service: IntegrationService = Depends(service_dependency)):
    principal.require(["integrations:write"])
    try:
        return await service.create(payload, principal)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{integration_id}", response_model=IntegrationResponse)
async def update_integration(integration_id: str, payload: IntegrationUpdateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), service: IntegrationService = Depends(service_dependency)):
    principal.require(["integrations:write"])
    try:
        return await service.update(integration_id, payload, principal)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{integration_id}/test", response_model=IntegrationTestResponse)
async def test_integration(integration_id: str, principal: EnterprisePrincipal = Depends(principal_dependency), service: IntegrationService = Depends(service_dependency)):
    principal.require(["integrations:write"])
    try:
        return await service.test(integration_id, principal)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{integration_id}/deliveries", response_model=DeliveryResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_delivery(integration_id: str, payload: DeliveryCreateRequest, principal: EnterprisePrincipal = Depends(principal_dependency), service: IntegrationService = Depends(service_dependency)):
    principal.require(["integrations:deliver"])
    try:
        return await service.enqueue_delivery(integration_id, payload, principal)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{integration_id}/deliveries", response_model=list[DeliveryResponse])
async def list_deliveries(integration_id: str, principal: EnterprisePrincipal = Depends(principal_dependency), service: IntegrationService = Depends(service_dependency)):
    principal.require(["integrations:read"])
    try:
        return await service.list_deliveries(integration_id, principal)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
