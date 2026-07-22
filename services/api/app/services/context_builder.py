from __future__ import annotations

from typing import List, Optional

from app.models.schemas import KbHit, RetrievedRule


class ContextBuilder:
    def build(self, rules: List[RetrievedRule], kb_hits: Optional[List[KbHit]] = None, graph_context: str = "") -> str:
        sections: list[str] = []
        if kb_hits:
            bullets = "\n".join(
                f"- [{hit.title} | score={hit.score}] {hit.text[:320]}"
                for hit in kb_hits[:3]
            )
            sections.append(
                "Relevant knowledge (ingested KB):\n"
                f"{bullets}\n\n"
                "Use these policy/SOP facts when answering. Prefer KB over guessing."
            )
        if rules:
            bullets = "\n".join(f"- {rule.rule_text}" for rule in rules[:3])
            sections.append(
                "Relevant operating lessons:\n"
                f"{bullets}\n\n"
                "Apply these lessons when relevant to the task. Do not bypass governance checks."
            )
        if graph_context:
            sections.append(graph_context)
        return "\n\n".join(sections)
