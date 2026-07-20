import { TraceMemoryClient } from "./client";
import type { AgentLifecycleEvent, ContextCandidate, TraceMemoryPluginConfig } from "./types";

export type { AgentLifecycleEvent, ContextCandidate, TraceMemoryPluginConfig } from "./types";
export { TraceMemoryClient } from "./client";

export function createTraceMemoryOpenClawPlugin(config: TraceMemoryPluginConfig) {
  const client = new TraceMemoryClient(config);

  return {
    name: "tracememory",
    displayName: "TraceMemory for OpenClaw",

    async onMessageReceived(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "message.received" });
    },

    async onTaskCreated(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "task.created" });
    },

    async onContextBuilt(input: {
      taskId?: string;
      task: string;
      candidates: ContextCandidate[];
      tokenBudget?: number;
      payload?: Record<string, unknown>;
    }) {
      const contextReceipt = await client.buildContext({
        task: input.task,
        agentType: config.agentId ?? "openclaw_agent",
        candidates: input.candidates,
        tokenBudget: input.tokenBudget,
      });
      await client.recordEvent({
        type: "context.built",
        taskId: input.taskId,
        payload: { ...(input.payload ?? {}), contextReceipt },
      });
      return contextReceipt;
    },

    async onToolCallRequested(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "tool.requested" });
    },

    async onToolCallCompleted(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "tool.completed" });
    },

    async onToolCallFailed(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "tool.failed" });
    },

    async onCheckpointRequested(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "checkpoint.requested" });
    },

    async onTaskModified(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "task.modified" });
    },

    async onFinalResponse(event: Omit<AgentLifecycleEvent, "type">) {
      return client.recordEvent({ ...event, type: "final.response" });
    },
  };
}
