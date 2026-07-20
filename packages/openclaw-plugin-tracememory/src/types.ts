export type TraceMemoryPluginConfig = {
  /** Base URL of the TraceMemory API server, e.g. http://localhost:8000 */
  apiUrl: string;
  /** API prefix used by TraceMemory. Defaults to /api. */
  apiPrefix?: string;
  /** Bearer/API key accepted by TraceMemory. */
  apiKey?: string;
  organisationId?: string;
  workspaceId?: string;
  projectId?: string;
  environmentId?: string;
  agentId?: string;
};

export type AgentLifecycleEvent = {
  type:
    | "message.received"
    | "task.created"
    | "prompt.build"
    | "context.built"
    | "tool.requested"
    | "tool.completed"
    | "tool.failed"
    | "agent.step.completed"
    | "checkpoint.requested"
    | "agent.error"
    | "task.modified"
    | "final.response";
  taskId?: string;
  traceId?: string;
  checkpointId?: string;
  runId?: string;
  payload?: Record<string, unknown>;
  createdAt?: string;
};

export type ContextCandidate = {
  source_ref: string;
  source_type?: string;
  title?: string;
  summary?: string;
  content?: string;
  token_estimate?: number;
  relevance_score?: number;
  freshness_score?: number;
  trust_score?: number;
  sensitivity_level?: "low" | "medium" | "high" | "secret";
  verification_status?: string;
  action?: "include" | "compress" | "redact" | "exclude" | "delegate" | "require_approval";
  metadata?: Record<string, unknown>;
};
