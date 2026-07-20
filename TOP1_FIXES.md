# TraceMemory Top-1 Hackathon Fixes

This version is tuned for remote RAISE judging where the demo carries the most weight.

## What changed

- Preserved the original Continuum-led UI as the judging source of truth.
- Added a clear **Without TraceMemory vs With TraceMemory** failure contrast inside the Agent Demo.
- Added a visible **Top-1 proof panel** showing Vultr stack status, trace ID, checkpoint ID, and receipt status.
- Added a prominent **Run top-1 recovery demo** button inside the preserved demo layout.
- The button calls `POST /api/demo/hackathon-10x` and auto-advances the visual recovery flow.
- If the API is unavailable, the UI falls back to deterministic local demo mode so the story is still judge-visible.
- `localhost:3000` now loads the preserved Continuum UI instead of the simplified v2 React card UI.
- README and judging notes now focus on one story: **agent crashes → checkpoint restored → task continues → receipt proves it**.

## Judge takeaway

TraceMemory is not another observability dashboard. It is **crash recovery for long-running AI agents**.
