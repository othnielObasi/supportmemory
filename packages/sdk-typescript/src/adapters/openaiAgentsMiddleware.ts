import { TraceMemoryClient } from "../client";
import type { Json } from "../types";
import { wrapTool } from "./toolWrapper";

export class TraceMemoryOpenAIAgentsMiddleware {
  constructor(
    private client: TraceMemoryClient,
    private taskId: string,
    private agentId: string,
  ) {}

  onAgentStart(instructions: string, metadata: Record<string, Json> = {}) {
    return this.client.recordEvent(this.taskId, "request_received", {
      framework: "openai-agents",
      agentId: this.agentId,
      instructions,
      metadata,
    });
  }

  onPlan(plan: Record<string, Json>) {
    return this.client.recordEvent(this.taskId, "plan_prepared", {
      framework: "openai-agents",
      agentId: this.agentId,
      plan,
    });
  }

  wrapTool<TArgs extends unknown[], TResult>(
    toolName: string,
    fn: (...args: TArgs) => Promise<TResult> | TResult,
    toolType: "read" | "write" | "external_action" | "unknown" = "read",
  ) {
    return wrapTool(this.client, this.taskId, fn, {
      toolName,
      toolType,
      checkpointAfter: toolType === "read",
    });
  }

  onFinalAnswer(answer: string, metadata: Record<string, Json> = {}) {
    return this.client.recordEvent(this.taskId, "final_answer", {
      framework: "openai-agents",
      agentId: this.agentId,
      answer,
      metadata,
    });
  }
}
