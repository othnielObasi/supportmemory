from __future__ import annotations

from typing import Dict, Optional

REQUESTERS = {
    's1': {'name': 'Priya Shah', 'email': 'priya.shah@acme.io', 'company': 'Acme Corp'},
    's2': {'name': 'Marcus Webb', 'email': 'marcus.webb@northwind.io', 'company': 'Northwind Retail'},
    's3': {'name': 'Priya Shah', 'email': 'priya.shah@acme.io', 'company': 'Acme Corp'},
    's4': {'name': 'Elena Torres', 'email': 'elena.torres@brightpath.io', 'company': 'Brightpath Media'},
    's5': {'name': 'Marcus Webb', 'email': 'marcus.webb@northwind.io', 'company': 'Northwind Retail'},
    's6': {'name': 'Priya Shah', 'email': 'priya.shah@acme.io', 'company': 'Acme Corp'},
    'c1': {'name': 'David Okafor', 'email': 'david.okafor@vertex-labs.io', 'company': 'Vertex Labs'},
    'c2': {'name': 'Hana Kobayashi', 'email': 'hana.kobayashi@quillfin.io', 'company': 'Quillfin'},
    'c3': {'name': 'David Okafor', 'email': 'david.okafor@vertex-labs.io', 'company': 'Vertex Labs'},
    'c4': {'name': 'Hana Kobayashi', 'email': 'hana.kobayashi@quillfin.io', 'company': 'Quillfin'},
    'c5': {'name': 'David Okafor', 'email': 'david.okafor@vertex-labs.io', 'company': 'Vertex Labs'},
    'c6': {'name': 'Hana Kobayashi', 'email': 'hana.kobayashi@quillfin.io', 'company': 'Quillfin'},
}

DATASETS = {
    'support_tickets': {
        None: {'items': [{'id': 's1', 'issue': 'billing delay', 'severity': 'medium'}, {'id': 's2', 'issue': 'login failure', 'severity': 'high'}], 'next_page_token': 'support_page_2'},
        'support_page_2': {'items': [{'id': 's3', 'issue': 'billing delay', 'severity': 'low'}, {'id': 's4', 'issue': 'password reset failure', 'severity': 'medium'}], 'next_page_token': 'support_page_3'},
        'support_page_3': {'items': [{'id': 's5', 'issue': 'login failure', 'severity': 'medium'}, {'id': 's6', 'issue': 'billing delay', 'severity': 'high'}], 'next_page_token': None},
    },
    'compliance_tickets': {
        None: {'items': [{'id': 'c1', 'issue': 'missing approval evidence', 'severity': 'high'}, {'id': 'c2', 'issue': 'unresolved DPIA checklist', 'severity': 'medium'}], 'next_page_token': 'compliance_page_2'},
        'compliance_page_2': {'items': [{'id': 'c3', 'issue': 'missing approval evidence', 'severity': 'medium'}, {'id': 'c4', 'issue': 'model card incomplete', 'severity': 'medium'}], 'next_page_token': 'compliance_page_3'},
        'compliance_page_3': {'items': [{'id': 'c5', 'issue': 'audit log missing', 'severity': 'high'}, {'id': 'c6', 'issue': 'missing approval evidence', 'severity': 'low'}], 'next_page_token': None},
    },
}
for _dataset in DATASETS.values():
    for _page in _dataset.values():
        for _item in _page['items']:
            _item['requester'] = REQUESTERS.get(_item['id'])


def fetch_tickets(dataset_type: str, page_token: Optional[str] = None) -> Dict:
    dataset = DATASETS.get(dataset_type)
    if not dataset:
        raise ValueError(f'Unknown dataset_type: {dataset_type}')
    page = dataset.get(page_token)
    if page is None:
        raise ValueError(f'Unknown page_token for {dataset_type}: {page_token}')
    return page


def summarise_items(items: list[dict]) -> str:
    counts: dict[str, int] = {}
    for item in items:
        issue = item.get('issue', 'unknown')
        counts[issue] = counts.get(issue, 0) + 1
    return '; '.join([f'{issue} ({count})' for issue, count in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)])
