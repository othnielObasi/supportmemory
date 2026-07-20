from tracememory import TraceMemoryClient

client = TraceMemoryClient(base_url="http://localhost:8000")
run = client.start_run(
    agent_id="ticket-investigation-agent",
    task="Analyse all support tickets and summarise recurring customer issues.",
)
task_id = run["task_id"]
client.record_event(task_id, "plan_prepared", {"plan": ["fetch tickets", "validate continuation", "summarise"]})
client.record_tool_trace(
    task_id,
    tool="fetch_support_tickets",
    input={"status": "open"},
    output={"items_count": 100, "next_page_token": "page_2"},
    validation={"condition": "continue until next_page_token is null", "passed": False},
)
checkpoint = client.save_checkpoint(task_id, "support_page_1_complete", {"next_page_token": "page_2"})
print({"task_id": task_id, "checkpoint": checkpoint})
