"""OpenAI Agents SDK-style TraceMemory middleware example."""

from tracememory import TraceMemoryClient, TraceMemoryOpenAIAgentsMiddleware

client = TraceMemoryClient(base_url="http://localhost:8000")
run = client.start_run(agent_id="openai-agent-example", task="Review compliance tickets")
task_id = run.get("task_id") or run.get("taskId")

middleware = TraceMemoryOpenAIAgentsMiddleware(client, task_id, agent_id="compliance-agent")
middleware.on_agent_start("Review compliance tickets and preserve runtime evidence.")
middleware.on_plan({"steps": ["retrieve", "validate", "summarize"]})


def fetch_compliance_tickets() -> dict:
    return {"count": 25, "next_page_token": None}


fetch_tool = middleware.wrap_tool("fetch_compliance_tickets", fetch_compliance_tickets)
fetch_tool()
middleware.on_final_answer("Compliance ticket review completed with checkpointed runtime state.")
