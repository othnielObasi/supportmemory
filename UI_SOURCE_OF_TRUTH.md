# UI Source of Truth

This hackathon package uses a light-theme design system — purple (#7c3aed) accent, Unbounded/Inter/Geist Mono typefaces — with five pages: Landing, Console, Agent Demo, Developers, Integrations, switchable via `showPage()`/`goToSection()` with no page reload.

The visual design must not be redesigned, restyled, darkened, simplified into cards, or converted into a different console aesthetic during further hardening.

Canonical UI file:

- `HACKATHON_UI.html`

Synced copies:

- `apps/console/public/hackathon-ui.html`
- `docs/assets/tracememory-hackathon-ui.html`

All three must stay byte-identical. If you edit one, copy it over the other two before committing.

Allowed changes:

- Text updates that clarify TraceMemory as agent recovery infrastructure
- Backend wiring around the existing demo structure (see "Live data wiring" below)
- README, API, Alibaba Cloud, and open-source packaging improvements

Not allowed:

- Replacing the original demo layout
- Changing the approved visual system (colors, type, page structure)
- Turning the demo into a toy card layout
- Creating a new UI from scratch

## Live data wiring

The Console and Agent Demo pages call the real backend when reachable:

- **Load live data** (Console) → `GET /api/demo/state` + `GET /api/system/status`, replaces sample stat cards and the runs table.
- **New run** (Agent Demo) → `POST /api/tasks/run`, captures a live `trace_id`.
- **View runtime evidence** (Agent Demo) → `GET /api/traces/{trace_id}/receipt`, opens the real signed receipt.

All three fail quietly to sample/scripted content if no backend is reachable (safe for judges opening the static file directly). Override the API base with `?api=https://your-host:8000` in the URL.

The core hackathon message remains:

> TraceMemory makes long-running AI agents recoverable — and gives them memory they can prove.
