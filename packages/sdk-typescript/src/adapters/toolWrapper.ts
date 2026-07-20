import { TraceMemoryClient } from "../client";
import type { Json } from "../types";

export type ToolType = "read" | "write" | "external_action" | "unknown";

export interface ToolWrapperConfig<TArgs extends unknown[] = unknown[], TResult = unknown> {
  toolName: string;
  toolType?: ToolType;
  checkpointAfter?: boolean;
  checkpointName?: string;
  validation?: Record<string, Json> | ((args: TArgs, result: TResult) => Record<string, Json>);
  observedSignals?: Record<string, Json> | ((args: TArgs, result: TResult) => Record<string, Json>);
  idempotencyKey?: string | ((args: TArgs) => string | undefined);
}

function toRecord(value: unknown): Record<string, Json> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, Json>;
  return { value: value as Json };
}

function resolveValue<TArgs extends unknown[], TResult>(
  value: Record<string, Json> | ((args: TArgs, result: TResult) => Record<string, Json>) | undefined,
  args: TArgs,
  result: TResult,
): Record<string, Json> {
  if (!value) return {};
  if (typeof value === "function") return value(args, result);
  return value;
}

export function wrapTool<TArgs extends unknown[], TResult>(
  client: TraceMemoryClient,
  taskId: string,
  fn: (...args: TArgs) => Promise<TResult> | TResult,
  config: ToolWrapperConfig<TArgs, TResult>,
): (...args: TArgs) => Promise<TResult> {
  return async (...args: TArgs) => {
    const toolType = config.toolType ?? "read";
    const idempotencyKey = typeof config.idempotencyKey === "function" ? config.idempotencyKey(args) : config.idempotencyKey;

    if ((toolType === "write" || toolType === "external_action") && idempotencyKey) {
      const action = await client.executeAction(taskId, {
        toolName: config.toolName,
        toolType,
        idempotencyKey,
        input: { args: args as unknown as Json[] },
      });
      const maybeReplay = action as Record<string, unknown>;
      if (maybeReplay.replayed || maybeReplay.duplicate) return (maybeReplay.result ?? action) as TResult;
    }

    const result = await fn(...args);
    await client.recordToolTrace(taskId, {
      tool: config.toolName,
      toolType,
      input: { args: args as unknown as Json[] },
      output: toRecord(result),
      validation: resolveValue(config.validation, args, result),
      observedSignals: resolveValue(config.observedSignals, args, result),
      idempotencyKey,
    });

    if (config.checkpointAfter) {
      await client.saveCheckpoint(taskId, {
        checkpointName: config.checkpointName ?? `${config.toolName}_complete`,
        state: { tool: config.toolName, result: toRecord(result) },
        resumeState: { currentStep: `after:${config.toolName}`, pendingActions: [] },
        metadata: { source: "wrapTool", toolType },
      });
    }

    return result;
  };
}
