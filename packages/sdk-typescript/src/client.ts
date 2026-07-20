import type { ActionExecutionInput, BuildContextInput, CheckpointInput, FireworksPlanInput, StartRunInput, ToolTraceInput, VoiceSummaryInput } from "./types";

export class TraceMemoryClient {
  constructor(private baseUrl: string, private apiKey?: string) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (this.apiKey) headers.Authorization = `Bearer ${this.apiKey}`;
    const res = await fetch(`${this.baseUrl}${path}`, { ...init, headers: { ...headers, ...(init.headers || {}) } });
    if (!res.ok) throw new Error(`TraceMemory request failed: ${res.status} ${await res.text()}`);
    return (await res.json()) as T;
  }

  startRun(input: StartRunInput) {
    return this.request("/api/tasks/run", {
      method: "POST",
      body: JSON.stringify({
        agent_id: input.agentId,
        task_description: input.task,
        dataset_type: input.datasetType ?? "support_tickets",
        task_version: input.taskVersion,
        parent_checkpoint_id: input.parentCheckpointId,
        simulate_restart: input.simulateRestart,
        task_modification: input.taskModification,
        idempotency_key: input.idempotencyKey,
      }),
    });
  }

  recoverTask(checkpointId: string, input: Partial<StartRunInput> = {}) {
    return this.request(`/api/tasks/recover`, {
      method: "POST",
      body: JSON.stringify({
        checkpoint_id: checkpointId,
        task_description: input.task,
        agent_id: input.agentId,
        dataset_type: input.datasetType,
        task_modification: input.taskModification,
        idempotency_key: input.idempotencyKey,
      }),
    });
  }

  recordEvent(taskId: string, code: string, payload: Record<string, unknown> = {}) {
    return this.request(`/api/runs/${taskId}/events`, { method: "POST", body: JSON.stringify({ code, payload }) });
  }

  recordToolTrace(taskId: string, trace: ToolTraceInput) {
    return this.request(`/api/runs/${taskId}/tool-traces`, {
      method: "POST",
      body: JSON.stringify({
        tool: trace.tool,
        tool_type: trace.toolType ?? "read",
        input: trace.input,
        output: trace.output,
        validation: trace.validation ?? {},
        observed_signals: trace.observedSignals ?? {},
        checkpoint_id: trace.checkpointId,
        trace_id: trace.traceId,
        idempotency_key: trace.idempotencyKey,
      }),
    });
  }

  saveCheckpoint(taskId: string, checkpoint: CheckpointInput) {
    return this.request(`/api/runs/${taskId}/checkpoints`, {
      method: "POST",
      body: JSON.stringify({
        checkpoint_name: checkpoint.checkpointName,
        state: checkpoint.state,
        resume_state: checkpoint.resumeState ?? {},
        safe_to_resume: checkpoint.safeToResume ?? true,
        requires_human_review: checkpoint.requiresHumanReview ?? false,
        metadata: checkpoint.metadata ?? {},
      }),
    });
  }

  restoreCheckpoint(checkpointId: string) {
    return this.request(`/api/checkpoints/${checkpointId}/restore`, { method: "POST", body: JSON.stringify({}) });
  }

  modifyTask(taskId: string, newTaskDescription: string, modification: string, parentCheckpointId?: string) {
    return this.request(`/api/tasks/${taskId}/modify`, {
      method: "POST",
      body: JSON.stringify({ new_task_description: newTaskDescription, modification, parent_checkpoint_id: parentCheckpointId }),
    });
  }

  approveMemory(taskId: string, rule: string, appliesTo: string[], confidence = 0.8, evidence: Record<string, unknown> = {}) {
    return this.request(`/api/runs/${taskId}/memory/approve`, {
      method: "POST",
      body: JSON.stringify({ rule, applies_to: appliesTo, confidence, evidence }),
    });
  }

  executeAction(taskId: string, input: ActionExecutionInput) {
    return this.request(`/api/runs/${taskId}/actions/execute`, {
      method: "POST",
      body: JSON.stringify({
        tool_name: input.toolName,
        tool_type: input.toolType ?? "external_action",
        idempotency_key: input.idempotencyKey,
        input: input.input ?? {},
      }),
    });
  }

  listEvents(taskId: string) {
    return this.request(`/api/runs/${taskId}/events`);
  }

  streamEvents(taskId: string): EventSource {
    return new EventSource(`${this.baseUrl}/api/runs/${taskId}/stream`);
  }

  generatePlan(input: FireworksPlanInput) {
    return this.request(`/api/ai/plan`, {
      method: "POST",
      body: JSON.stringify({ task_description: input.task, run_events: input.runEvents ?? [], checkpoint_id: input.checkpointId, task_version: input.taskVersion ?? 1 }),
    });
  }

  synthesizeRunSummary(input: VoiceSummaryInput) {
    return this.request(`/api/voice/run-summary`, {
      method: "POST",
      body: JSON.stringify({ text: input.text, voice_id: input.voiceId, run_id: input.runId, checkpoint_id: input.checkpointId }),
    });
  }


  buildContext(input: BuildContextInput) {
    return this.request(`/api/context-health/build`, {
      method: "POST",
      body: JSON.stringify({
        task: input.task,
        agent_type: input.agentType ?? "external_agent",
        token_budget: input.tokenBudget ?? 12000,
        persist_receipt: input.persistReceipt ?? true,
        organisation_id: input.organisationId ?? "org_default",
        workspace_id: input.workspaceId ?? "wrk_default",
        project_id: input.projectId ?? "prj_default",
        environment_id: input.environmentId ?? "dev",
        candidate_context: input.candidateContext.map((candidate) => ({
          source_ref: candidate.sourceRef,
          source_type: candidate.sourceType,
          title: candidate.title,
          summary: candidate.summary,
          content: candidate.content,
          token_estimate: candidate.tokenEstimate,
          relevance_score: candidate.relevanceScore,
          freshness_score: candidate.freshnessScore,
          trust_score: candidate.trustScore,
          sensitivity_level: candidate.sensitivityLevel,
          verification_status: candidate.verificationStatus,
          action: candidate.action,
          metadata: candidate.metadata ?? {},
        })),
      }),
    });
  }

  getContextReceipts() {
    return this.request(`/api/context-health/receipts`);
  }

  partnerStatus() {
    return this.request(`/api/partners/status`);
  }
}
