from app.models.schemas import (
    ActionExecutionRequest,
    CheckpointRestoreResponse,
    RecordToolTraceRequest,
    ResumeState,
    RunTaskRequest,
    SystemStatus,
    ToolTrace,
    ToolType,
    stable_hash,
)
from app.api import RUN_EVENT_DEFINITIONS
from app.db.postgres import PRODUCTION_COLLECTIONS


def test_run_events_include_production_coordination_states():
    codes = {code for code, _, _ in RUN_EVENT_DEFINITIONS}
    assert 'checkpoint_saved' in codes
    assert 'checkpoint_restored' in codes
    assert 'task_modified' in codes
    assert 'memory_created_or_retrieved' in codes


def test_run_task_request_supports_idempotency_and_recovery():
    payload = RunTaskRequest(
        task_description='Analyse support tickets',
        idempotency_key='idem-1',
        parent_checkpoint_id='chk_123',
        simulate_restart=True,
    )
    assert payload.idempotency_key == 'idem-1'
    assert payload.parent_checkpoint_id == 'chk_123'
    assert payload.simulate_restart is True


def test_checkpoint_restore_response_contains_resumable_state():
    response = CheckpointRestoreResponse(
        checkpoint_id='chk_001',
        task_id='task_001',
        trace_id='trace_001',
        agent_id='agent_001',
        task_version=2,
        recovery_status='restored',
        resume_from='fetch_remaining_records',
        state={'task_description': 'continue'},
        agent_state=ResumeState(current_step='fetch_remaining_records', page_token='page_2'),
        safe_to_resume=True,
    )
    assert response.safe_to_resume is True
    assert response.agent_state.page_token == 'page_2'


def test_tool_trace_contract_hashes_inputs_and_outputs():
    input_payload = {'page_token': 'page_2'}
    output_payload = {'items_count': 50, 'next_page_token': None}
    trace = ToolTrace(
        task_id='task_001',
        tool_name='fetch_support_tickets',
        tool_type=ToolType.read,
        input_hash=stable_hash(input_payload),
        output_hash=stable_hash(output_payload),
        observed_signals={'next_page_token': None},
        validation={'passed': True},
    )
    assert trace.input_hash != trace.output_hash
    assert trace.validation['passed'] is True


def test_developer_tool_trace_request_supports_observed_signals():
    payload = RecordToolTraceRequest(
        tool='fetch_support_tickets',
        input={'page': 1},
        output={'items_count': 100},
        observed_signals={'next_page_token': 'page_2'},
        validation={'passed': False},
    )
    assert payload.observed_signals['next_page_token'] == 'page_2'


def test_action_execution_requires_idempotency_key():
    payload = ActionExecutionRequest(
        tool_name='send_email',
        idempotency_key='email-task-001',
        input={'to': 'ops@example.com'},
    )
    assert payload.idempotency_key == 'email-task-001'


def test_system_status_contract_supports_infra_claim():
    status = SystemStatus(
        status='ok',
        app='TraceMemory',
        environment='production',
        database='PostgreSQL / JSONB durable execution store',
        connected=True,
        aws_ready=True,
        collections=['agent_runs', 'task_checkpoints'],
        indexes_ready=True,
        production_features=['task_checkpoints'],
    )
    assert status.database == 'PostgreSQL / JSONB durable execution store'
    assert status.aws_ready is True


def test_production_collections_include_hardening_records():
    assert 'tool_traces' in PRODUCTION_COLLECTIONS
    assert 'governor_decisions' in PRODUCTION_COLLECTIONS
    assert 'action_executions' in PRODUCTION_COLLECTIONS
    assert 'idempotency_keys' in PRODUCTION_COLLECTIONS


def test_sdk_adapter_files_exist():
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    assert (root / 'packages/sdk-python/tracememory/adapters/langgraph.py').exists()
    assert (root / 'packages/sdk-python/tracememory/adapters/crewai.py').exists()
    assert (root / 'packages/sdk-python/tracememory/adapters/openai_agents.py').exists()
    assert (root / 'packages/sdk-python/tracememory/adapters/tool_wrapper.py').exists()
    assert (root / 'packages/sdk-typescript/src/adapters/langgraphAdapter.ts').exists()
    assert (root / 'packages/sdk-typescript/src/adapters/crewaiAdapter.ts').exists()
    assert (root / 'packages/sdk-typescript/src/adapters/openaiAgentsMiddleware.ts').exists()
    assert (root / 'packages/sdk-typescript/src/adapters/toolWrapper.ts').exists()
