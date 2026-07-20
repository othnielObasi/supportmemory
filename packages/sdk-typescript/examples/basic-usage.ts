import { TraceMemoryClient } from "../src";

const client = new TraceMemoryClient("http://localhost:8000");

async function main() {
  const run: any = await client.startRun({
    agentId: "ticket-investigation-agent",
    task: "Analyse all support tickets and summarise recurring customer issues.",
  });

  await client.recordEvent(run.task_id, "plan_prepared", { plan: ["fetch", "validate", "summarise"] });
  await client.saveCheckpoint(run.task_id, {
    checkpointName: "support_page_1_complete",
    state: { next_page_token: "page_2" },
  });
}

main().catch(console.error);
