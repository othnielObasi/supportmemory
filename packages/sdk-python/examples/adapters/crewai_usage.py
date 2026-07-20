"""CrewAI-style TraceMemory adapter example."""

from tracememory import TraceMemoryClient, TraceMemoryCrewAIAdapter

client = TraceMemoryClient(base_url="http://localhost:8000")
run = client.start_run(agent_id="crewai-example", task="Coordinate vendor review")
task_id = run.get("task_id") or run.get("taskId")

adapter = TraceMemoryCrewAIAdapter(client, task_id, crew_name="vendor-review-crew")


def collect_vendor_evidence() -> dict:
    return {"status": "complete", "missing": []}


review_task = adapter.wrap_task("collect_vendor_evidence", collect_vendor_evidence)
review_task()
adapter.record_handoff("research-agent", "review-agent", {"reason": "evidence collected"})
