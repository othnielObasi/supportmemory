import { TraceMemoryClient } from "../client";
import type { Json } from "../types";
import { wrapTool } from "./toolWrapper";

export class TraceMemoryCrewAIAdapter {
  constructor(
    private client: TraceMemoryClient,
    private taskId: string,
    private crewName = "crew",
  ) {}

  wrapTask<TArgs extends unknown[], TResult>(
    taskName: string,
    fn: (...args: TArgs) => Promise<TResult> | TResult,
  ): (...args: TArgs) => Promise<TResult> {
    return async (...args: TArgs) => {
      await this.client.recordEvent(this.taskId, "plan_prepared", {
        framework: "crewai",
        crew: this.crewName,
        task: taskName,
      });
      const result = await fn(...args);
      await this.client.saveCheckpoint(this.taskId, {
        checkpointName: `${this.crewName}.${taskName}.complete`,
        state: { task: taskName, result: JSON.parse(JSON.stringify(result)) as Json },
        resumeState: { currentStep: `after:${taskName}`, pendingActions: [] },
        metadata: { framework: "crewai", crew: this.crewName, task: taskName },
      });
      return result;
    };
  }

  wrapTool<TArgs extends unknown[], TResult>(
    toolName: string,
    fn: (...args: TArgs) => Promise<TResult> | TResult,
    toolType: "read" | "write" | "external_action" | "unknown" = "read",
  ) {
    return wrapTool(this.client, this.taskId, fn, { toolName, toolType });
  }

  recordHandoff(fromAgent: string, toAgent: string, context: Record<string, Json>) {
    return this.client.recordEvent(this.taskId, "task_modified", {
      framework: "crewai",
      crew: this.crewName,
      handoff: { from: fromAgent, to: toAgent },
      context,
    });
  }
}
