# One-Minute Demo Script

## 0–8 seconds

Long-running agents fail when they lose task state, repeat tools, or cannot recover after interruption.

## 8–15 seconds

This is TraceMemory running as a Vultr-deployable recovery layer for agents.

## 15–30 seconds

We start a long-running ticket investigation. TraceMemory saves the task contract, checks context health, traces MCP-style tools, and saves a checkpoint.

## 30–45 seconds

Now we simulate a failure. Without TraceMemory, the agent would restart, repeat work, or produce an incomplete answer. With TraceMemory, the latest trusted checkpoint is restored.

## 45–55 seconds

The agent continues after the task is updated to include compliance tickets, while earlier evidence is preserved.

## 55–60 seconds

TraceMemory generates a receipt linking the task, context warning, tool evidence, checkpoint, recovery event, and final output.
