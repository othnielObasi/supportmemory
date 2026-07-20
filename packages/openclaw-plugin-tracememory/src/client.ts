import type { AgentLifecycleEvent, ContextCandidate, TraceMemoryPluginConfig } from "./types";

export class TraceMemoryClient {
  private readonly config: TraceMemoryPluginConfig;

  constructor(config: TraceMemoryPluginConfig) {
    this.config = config;
  }

  private headers(): Record<string, string> {
    const headers: Record<string, string> = { "content-type": "application/json" };
    if (this.config.apiKey) {
      headers.Authorization = `Bearer ${this.config.apiKey}`;
      headers["x-tracememory-api-key"] = this.config.apiKey;
    }
    return headers;
  }

  private apiBase(): string {
    const base = this.config.apiUrl.replace(/\/$/, "");
    const prefix = (this.config.apiPrefix ?? "/api").replace(/^\/?/, "/").replace(/\/$/, "");
    return base.endsWith(prefix) ? base : `${base}${prefix}`;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const normalizedPath = path.startsWith("/") ? path : `/${path}`;
    const response = await fetch(`${this.apiBase()}${normalizedPath}`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(`TraceMemory request failed ${response.status}: ${text}`);
    }
    return (await response.json()) as T;
  }

  async recordEvent(event: AgentLifecycleEvent): Promise<unknown> {
    const taskId = event.taskId ?? "openclaw_task_pending";
    return this.post(`/runs/${encodeURIComponent(taskId)}/events`, {
      task_id: taskId,
      trace_id: event.traceId,
      checkpoint_id: event.checkpointId,
      code: event.type,
      label: event.type,
      status: event.type.includes("failed") || event.type.includes("error") ? "failed" : "complete",
      description: `OpenClaw lifecycle event: ${event.type}`,
      payload: event.payload ?? {},
    });
  }

  async recordToolTrace(input: {
    taskId: string;
    runId?: string;
    traceId?: string;
    checkpointId?: string;
    toolName: string;
    toolType?: "read" | "write" | "external_action" | "unknown";
    toolInput?: Record<string, unknown>;
    toolOutput?: Record<string, unknown>;
    validation?: Record<string, unknown>;
    observedSignals?: Record<string, unknown>;
    idempotencyKey?: string;
  }): Promise<unknown> {
    return this.post(`/runs/${encodeURIComponent(input.taskId)}/tool-traces`, {
      tool: input.toolName,
      tool_type: input.toolType ?? "unknown",
      input: input.toolInput ?? {},
      output: input.toolOutput ?? {},
      validation: input.validation ?? {},
      observed_signals: input.observedSignals ?? {},
      checkpoint_id: input.checkpointId,
      trace_id: input.traceId,
      idempotency_key: input.idempotencyKey,
    });
  }

  async buildContext(input: {
    task: string;
    agentType?: string;
    candidates: ContextCandidate[];
    tokenBudget?: number;
  }): Promise<unknown> {
    return this.post("/context-health/build", {
      task: input.task,
      agent_type: input.agentType ?? this.config.agentId ?? "openclaw_agent",
      organisation_id: this.config.organisationId ?? "org_default",
      workspace_id: this.config.workspaceId ?? "wrk_default",
      project_id: this.config.projectId ?? "prj_default",
      environment_id: this.config.environmentId ?? "dev",
      token_budget: input.tokenBudget ?? 12000,
      candidate_context: input.candidates,
      persist_receipt: true,
    });
  }
}
