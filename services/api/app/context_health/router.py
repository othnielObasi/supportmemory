from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.context_health.schemas import ContextBuildRequest, ContextBuildResponse, ContextReceipt, DemoScenario
from app.context_health.service import ContextHealthService
from app.db.postgres import PostgresStore

router = APIRouter()
service = ContextHealthService()


def get_store() -> PostgresStore:
    from app.main import store
    return store


@router.post("/build", response_model=ContextBuildResponse)
async def build_context(payload: ContextBuildRequest, store: PostgresStore = Depends(get_store)) -> ContextBuildResponse:
    """Build a clean context bundle and persist a Context Receipt."""
    response, receipt = service.build_context(payload)
    if payload.persist_receipt:
        await store.insert_one("context_receipts", receipt.model_dump(mode="json"))
    return response


@router.get("/scenarios", response_model=list[DemoScenario])
async def list_scenarios() -> list[DemoScenario]:
    return service.scenarios()


@router.post("/scenarios/{scenario_id}/run", response_model=ContextBuildResponse)
async def run_scenario(scenario_id: str, store: PostgresStore = Depends(get_store)) -> ContextBuildResponse:
    scenarios = {scenario.scenario_id: scenario for scenario in service.scenarios()}
    scenario = scenarios.get(scenario_id)
    if not scenario:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scenario not found")
    payload = ContextBuildRequest(
        task=scenario.task,
        agent_type=scenario.agent_type,
        token_budget=scenario.token_budget,
        candidate_context=scenario.candidate_context,
        persist_receipt=True,
    )
    response, receipt = service.build_context(payload)
    await store.insert_one("context_receipts", receipt.model_dump(mode="json"))
    return response


@router.get("/receipts", response_model=list[ContextReceipt])
async def list_receipts(store: PostgresStore = Depends(get_store)) -> list[ContextReceipt]:
    docs = await store.find_many("context_receipts", {}, limit=100, sort=[("created_at", -1)])
    return [ContextReceipt(**doc) for doc in docs]
