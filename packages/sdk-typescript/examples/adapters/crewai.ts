import { TraceMemoryClient, TraceMemoryCrewAIAdapter } from "../../src";

const tm = new TraceMemoryClient("http://localhost:8000", process.env.TRACEMEMORY_API_KEY);
const run = await tm.startRun({ agentId: "crewai-example", task: "Coordinate vendor review" }) as { task_id?: string; taskId?: string };
const taskId = run.task_id ?? run.taskId ?? "task_local";

const adapter = new TraceMemoryCrewAIAdapter(tm, taskId, "vendor-review-crew");
const reviewTask = adapter.wrapTask("collect_vendor_evidence", async () => ({ status: "complete", missing: [] }));
await reviewTask();
await adapter.recordHandoff("research-agent", "review-agent", { reason: "evidence collected" });
