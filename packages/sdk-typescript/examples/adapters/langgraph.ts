import { TraceMemoryClient, TraceMemoryLangGraphAdapter } from "../../src";

const tm = new TraceMemoryClient("http://localhost:8000", process.env.TRACEMEMORY_API_KEY);
const run = await tm.startRun({ agentId: "langgraph-example", task: "Investigate claim documents" }) as { task_id?: string; taskId?: string };
const taskId = run.task_id ?? run.taskId ?? "task_local";

const adapter = new TraceMemoryLangGraphAdapter(tm, taskId, "claims-graph");

const retrieveNode = adapter.wrapNode("retrieve", async (state: Record<string, unknown>) => {
  return { ...state, documents: [{ id: "doc_1", title: "Evidence" }] } as Record<string, never>;
});

await retrieveNode({ query: "missing evidence" } as Record<string, never>);
