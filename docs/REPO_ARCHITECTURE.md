# TraceMemory Repository Architecture

TraceMemory is organised as a clean monorepo so infrastructure and example agents can evolve independently.

## Core infrastructure

- `services/api`: FastAPI service exposing run, event, checkpoint, recovery, memory, and system-status endpoints.
- `packages/sdk-python`: Python client for agent developers.
- `packages/sdk-typescript`: TypeScript client for web/Node agent developers.
- `apps/console`: infrastructure console for operators and judges.

## Example agent

- `examples/ticket-investigation-agent`: reference domain agent showing how to call the SDK/API.
- `apps/ticket-agent-demo`: ChatGPT-style UI for the example agent.

## Separation principle

The agent consumes TraceMemory through SDK/API contracts. It should not depend on private internals of the core runtime service.
