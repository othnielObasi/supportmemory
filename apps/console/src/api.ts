export type ApiState = "checking" | "online" | "degraded" | "offline";

export interface SystemStatus {
  status: string;
  connected: boolean;
  environment: string;
  model_routing?: Record<string, string>;
}

export interface TenantContext {
  organisation_id: string;
  workspace_id: string;
  project_id: string;
  environment_id: string;
}

export interface EnterpriseContext {
  principal: TenantContext;
  role: string;
  scopes: string[];
  auth_required: boolean;
}

export interface RetrievedRule {
  rule_id: string;
  score: number;
  rule_text: string;
  category?: string;
  evidence_ids?: string[];
}

export interface GraphPath {
  node_ids: string[];
  relations: string[];
  evidence_ids: string[];
  score: number;
  explanation?: string;
}

export interface KbHit {
  chunk_id: string;
  document_id: string;
  title: string;
  score: number;
  text: string;
  source_type?: string;
  evidence_ids?: string[];
}

export interface RunEvent {
  code: string;
  label: string;
  status: "complete" | "pending" | "failed";
  description: string;
  timestamp?: string;
}

export interface TaskRunResponse {
  task_id: string;
  trace_id: string;
  status: string;
  final_output: string;
  failure_type: string;
  retrieved_rules: RetrievedRule[];
  context_prefix: string;
  run_events: RunEvent[];
  checkpoint_id?: string;
  memory_record_id?: string;
  reflection_id?: string;
  learned_rule_id?: string;
  context_receipt_id?: string;
  model_trace?: Record<string, unknown>;
  investigation_report?: string;
  tool_investigation_summary?: string;
}

export interface ConversationMessage {
  message_id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  metadata?: Record<string, unknown>;
  created_at?: string;
}

export interface Conversation {
  conversation_id: string;
  user_id: string;
  title: string;
  channel: string;
  message_count: number;
  messages: ConversationMessage[];
  updated_at?: string;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail || `Request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

const queryBase = new URLSearchParams(window.location.search).get("api");
const baseUrl = (queryBase || import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "");
let tenantContext: TenantContext = {
  organisation_id: localStorage.getItem("sm.organisation") || "org_default",
  workspace_id: localStorage.getItem("sm.workspace") || "wrk_default",
  project_id: localStorage.getItem("sm.project") || "prj_default",
  environment_id: localStorage.getItem("sm.environment") || "dev",
};

export function setApiTenant(context: TenantContext) {
  tenantContext = context;
  localStorage.setItem("sm.organisation", context.organisation_id);
  localStorage.setItem("sm.workspace", context.workspace_id);
  localStorage.setItem("sm.project", context.project_id);
  localStorage.setItem("sm.environment", context.environment_id);
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 45_000): Promise<T> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort("timeout"), timeoutMs);
  const token = sessionStorage.getItem("supportmemory.access_token");
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      signal: init.signal || controller.signal,
      headers: {
        Accept: "application/json",
        ...(init.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        "X-Organisation-Id": tenantContext.organisation_id,
        "X-Workspace-Id": tenantContext.workspace_id,
        "X-Project-Id": tenantContext.project_id,
        "X-Environment-Id": tenantContext.environment_id,
        ...init.headers,
      },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({ detail: response.statusText }));
      throw new ApiError(response.status, typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
    }
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError") throw new Error("Request timed out. Try again.");
    throw new Error(error instanceof Error ? error.message : "Network request failed");
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  baseUrl,
  enterpriseContext: () => request<EnterpriseContext>("/api/enterprise/context", {}, 8_000),
  status: () => request<SystemStatus>("/api/system/status", {}, 8_000),
  demoState: () => request<Record<string, unknown>>("/api/demo/state"),
  getUser: (userId: string, organisationId: string, workspaceId: string) =>
    request<Record<string, unknown>>(`/api/preferences/user/${encodeURIComponent(userId)}?organisation_id=${encodeURIComponent(organisationId)}&workspace_id=${encodeURIComponent(workspaceId)}`),
  listConversations: (userId: string, organisationId: string, workspaceId: string) =>
    request<Conversation[]>(`/api/conversations/user/${encodeURIComponent(userId)}?organisation_id=${encodeURIComponent(organisationId)}&workspace_id=${encodeURIComponent(workspaceId)}`),
  getConversation: (conversationId: string, organisationId: string, workspaceId: string) =>
    request<Conversation>(`/api/conversations/${encodeURIComponent(conversationId)}?organisation_id=${encodeURIComponent(organisationId)}&workspace_id=${encodeURIComponent(workspaceId)}`),
  createConversation: (body: Record<string, unknown>) => request<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify(body) }),
  addMessage: (conversationId: string, body: Record<string, unknown>, organisationId: string, workspaceId: string) =>
    request<Conversation>(`/api/conversations/${encodeURIComponent(conversationId)}/messages?organisation_id=${encodeURIComponent(organisationId)}&workspace_id=${encodeURIComponent(workspaceId)}`, { method: "POST", body: JSON.stringify(body) }),
  runTask: (body: Record<string, unknown>, signal?: AbortSignal) =>
    request<TaskRunResponse>("/api/tasks/run", { method: "POST", body: JSON.stringify(body), signal }, 90_000),
  searchKb: (body: Record<string, unknown>) => request<{ hits: KbHit[]; context_prefix: string }>("/api/kb/search", { method: "POST", body: JSON.stringify(body) }),
  traverseGraph: (body: Record<string, unknown>) => request<GraphPath[]>("/api/graph/traverse", { method: "POST", body: JSON.stringify(body) }),
  executeAction: (taskId: string, body: Record<string, unknown>) =>
    request<{ action_id: string; replayed: boolean; decision: string; result: Record<string, unknown> }>(`/api/runs/${encodeURIComponent(taskId)}/actions/execute`, { method: "POST", body: JSON.stringify(body) }),
  receipt: (traceId: string) => request<Record<string, unknown>>(`/api/traces/${encodeURIComponent(traceId)}/receipt`),
};
