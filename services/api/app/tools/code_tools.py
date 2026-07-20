from __future__ import annotations

from typing import Dict, Optional

# Simulated evidence for the coding-agent demo scenario: an async auth-module
# refactor that hits a real test failure (async DB init ordering), matching
# the narrative in examples/demo-scenarios/coding-agent.scenario.js.
REFACTOR_RUNS = {
    'code_refactor_evidence': {
        None: {
            'items': [
                {'id': 'auth_session', 'file': 'auth/session.py', 'change': 'convert to async', 'test_result': 'failed', 'reason': 'async db init before pool ready'},
                {'id': 'auth_tokens', 'file': 'auth/tokens.py', 'change': 'convert to async', 'test_result': 'failed', 'reason': 'async db init before pool ready'},
                {'id': 'auth_middleware', 'file': 'auth/middleware.py', 'change': 'convert to async', 'test_result': 'passed'},
                {'id': 'auth_utils', 'file': 'auth/utils.py', 'change': 'convert to async', 'test_result': 'passed'},
            ],
            'next_page_token': None,
        },
    },
    # A second, related task: same rule applied to a different module. This is
    # what "Extend" in the demo narrative refers to — the approved memory rule
    # (init the async DB pool before any module that runs migrations on import)
    # gets applied before planning, so the same class of failure doesn't recur.
    'code_refactor_evidence_v2': {
        None: {
            'items': [
                {'id': 'billing_session', 'file': 'billing/session.py', 'change': 'convert to async', 'test_result': 'passed'},
                {'id': 'billing_ledger', 'file': 'billing/ledger.py', 'change': 'convert to async', 'test_result': 'passed'},
            ],
            'next_page_token': None,
        },
    },
}


def run_refactor_step(dataset_type: str, page_token: Optional[str] = None) -> Dict:
    dataset = REFACTOR_RUNS.get(dataset_type)
    if not dataset:
        raise ValueError(f'Unknown dataset_type: {dataset_type}')
    page = dataset.get(page_token)
    if page is None:
        raise ValueError(f'Unknown page_token for {dataset_type}: {page_token}')
    return page


def summarise_refactor(items: list[dict]) -> str:
    passed = sum(1 for i in items if i.get('test_result') == 'passed')
    failed = sum(1 for i in items if i.get('test_result') == 'failed')
    files = ', '.join(sorted({i.get('file', '?') for i in items}))
    failure_reasons = sorted({i.get('reason') for i in items if i.get('test_result') == 'failed' and i.get('reason')})
    reason_str = f' ({"; ".join(failure_reasons)})' if failure_reasons else ''
    return f'{passed} passed, {failed} failed across {files}{reason_str}'
