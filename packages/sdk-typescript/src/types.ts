export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

export interface StartRunInput {
  agentId: string;
  task: string;
  datasetType?: string;
  taskVersion?: number;
  parentCheckpointId?: string;
  simulateRestart?: boolean;
  taskModification?: string;
  idempotencyKey?: string;
}

export interface ToolTraceInput {
  tool: string;
  toolType?: "read" | "write" | "external_action" | "unknown";
  input: Record<string, Json>;
  output: Record<string, Json>;
  validation?: Record<string, Json>;
  observedSignals?: Record<string, Json>;
  checkpointId?: string;
  traceId?: string;
  idempotencyKey?: string;
}

export interface ResumeStateInput {
  currentStep?: string;
  pageToken?: string | null;
  partialResultsRef?: string | null;
  partialResults?: Record<string, Json>[];
  validatedRecords?: number;
  pendingActions?: Record<string, Json>[];
  observedSignals?: Record<string, Json>;
}

export interface CheckpointInput {
  checkpointName: string;
  state: Record<string, Json>;
  resumeState?: ResumeStateInput;
  safeToResume?: boolean;
  requiresHumanReview?: boolean;
  metadata?: Record<string, Json>;
}

export interface ActionExecutionInput {
  toolName: string;
  toolType?: "write" | "external_action" | "read" | "unknown";
  idempotencyKey: string;
  input?: Record<string, Json>;
}

export interface FireworksPlanInput {
  task: string;
  runEvents?: string[];
  checkpointId?: string;
  taskVersion?: number;
}

export interface VoiceSummaryInput {
  text: string;
  voiceId?: string;
  runId?: string;
  checkpointId?: string;
}


export interface ContextCandidateInput {
  sourceRef: string;
  sourceType?: string;
  title?: string;
  summary?: string;
  content?: string;
  tokenEstimate?: number;
  relevanceScore?: number;
  freshnessScore?: number;
  trustScore?: number;
  sensitivityLevel?: "low" | "medium" | "high" | "secret";
  verificationStatus?: string;
  action?: "include" | "compress" | "redact" | "exclude" | "delegate" | "require_approval";
  metadata?: Record<string, Json>;
}

export interface BuildContextInput {
  task: string;
  agentType?: string;
  tokenBudget?: number;
  persistReceipt?: boolean;
  candidateContext: ContextCandidateInput[];
  organisationId?: string;
  workspaceId?: string;
  projectId?: string;
  environmentId?: string;
}
