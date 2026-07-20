import { TraceMemoryClient } from "../client";
import type { Json } from "../types";

export type GraphState = Record<string, Json>;

export class TraceMemoryLangGraphAdapter {
  constructor(
    private client: TraceMemoryClient,
    private taskId: string,
    private graphName = "langgraph",
  ) {}

  wrapNode<TState extends GraphState>(
    nodeName: string,
    fn: (state: TState) => Promise<TState> | TState,
  ): (state: TState) => Promise<TState> {
    return async (state: TState) => {
      await this.client.recordEvent(this.taskId, "tool_execution_started", {
        framework: "langgraph",
        graph: this.graphName,
        node: nodeName,
      });
      const result = await fn(state);
      const checkpoint = await this.client.saveCheckpoint(this.taskId, {
        checkpointName: `${this.graphName}.${nodeName}.complete`,
        state: { inputState: state, outputState: result },
        resumeState: { currentStep: `after:${nodeName}`, pendingActions: [] },
        metadata: { framework: "langgraph", graph: this.graphName, node: nodeName },
      });
      await this.client.recordEvent(this.taskId, "checkpoint_saved", {
        framework: "langgraph",
        node: nodeName,
        checkpoint,
      });
      return result;
    };
  }

  async restoreState(checkpointId: string): Promise<Record<string, unknown>> {
    const restored = await this.client.restoreCheckpoint(checkpointId) as Record<string, unknown>;
    await this.client.recordEvent(this.taskId, "checkpoint_restored", {
      framework: "langgraph",
      checkpointId,
    });
    return (restored.resume_state ?? restored.resumeState ?? restored.state ?? {}) as Record<string, unknown>;
  }

  recordEdges(edges: string[]) {
    return this.client.recordEvent(this.taskId, "plan_prepared", {
      framework: "langgraph",
      graph: this.graphName,
      edges,
    });
  }
}

export const TraceMemoryCheckpointer = TraceMemoryLangGraphAdapter;
