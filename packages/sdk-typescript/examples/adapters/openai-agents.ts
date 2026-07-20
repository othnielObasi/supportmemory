import { TraceMemoryClient, TraceMemoryOpenAIAgentsMiddleware } from "../../src";

const tm = new TraceMemoryClient("http://localhost:8000", process.env.TRACEMEMORY_API_KEY);
const run = await tm.startRun({ agentId: "openai-agent-example", task: "Review compliance tickets" }) as { task_id?: string; taskId?: string };
const taskId = run.task_id ?? run.taskId ?? "task_local";

const middleware = new TraceMemoryOpenAIAgentsMiddleware(tm, taskId, "compliance-agent");
await middleware.onAgentStart("Review compliance tickets and preserve runtime evidence.");
await middleware.onPlan({ steps: ["retrieve", "validate", "summarize"] });

const fetchTickets = middleware.wrapTool("fetch_compliance_tickets", async () => ({ count: 25, next_page_token: null }));
await fetchTickets();
await middleware.onFinalAnswer("Compliance ticket review completed with checkpointed runtime state.");
