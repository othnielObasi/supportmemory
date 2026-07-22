# UI Source of Truth

SupportMemory uses the Figma file [supportmemory-ui](https://www.figma.com/design/nGKi7cAk6NH1GtjNdqZnXT/tracememory-ui) as the design source of truth.

## Canonical frames (Figma)

| Frame | Role |
|---|---|
| `supportmemory-v2` | Marketing landing |
| `capabilities-page` | Capabilities |
| `architecture-page` | Architecture |
| `SupportMemory - Dashboard` | Primary product UI (investigations + inspector) |

Removed from the file:

- `supportmemory-landing` (superseded by v2)
- `HTML-Export-Code`

## Implemented UI

Production console source:

- `apps/console/src/main.tsx` — application shell and interaction model
- `apps/console/src/api.ts` — typed, timeout-aware API client
- `apps/console/src/styles.css` — responsive production design system

The established product and marketing pages are served from `apps/console/index.html`.
The operator workspace is a separate production entry point at `/workspace.html`.

Hero asset:

- `assets/hero-supportmemory.jpg`
- `apps/console/public/assets/hero-supportmemory.jpg`

### Design system

- Accent: amber `#f59e0b` → `#ff5226`
- Dark surfaces: `#0f1419`
- Light surfaces: `#fbf9f5` / `#f9fafb`
- Type: Instrument Serif (display) · Geist · Geist Mono
- Pages (client-side, no reload): Landing · Capabilities · Architecture · **Dashboard**

### Production workspace (priority surface)

Three responsive regions:

1. Live investigation inbox with explicit connected/offline/empty states
2. Durable conversation workspace with reply/note modes and governed actions
3. Evidence drawer separating memory, graph relationships, execution state and receipts

### Live data wiring

Typed client: `apps/console/src/api.ts`.

| UI control | API |
|---|---|
| **Ask SupportMemory…** (composer) | `POST /api/tasks/run` + `POST /api/kb/search` |
| **+ New investigation** / **Pull helpdesk ticket** | `POST /api/connectors/helpdesk/mock` → `POST /api/tasks/run` |
| **Run recovery demo** | `POST /api/demo/failure-recovery` (+ KB search) |
| **Load live runs** | `GET /api/demo/state` + `GET /api/system/status` |
| **View receipt** | `GET /api/traces/{trace_id}/receipt` |
| **Seed demo KB** | `POST /api/kb/seed-demo` |
| **Search KB** | `POST /api/kb/search` |
| **Ingest text** | `POST /api/kb/ingest` |
| **Upload PDF** | `POST /api/kb/ingest/pdf` |
| **KB docs list** | `GET /api/kb/documents` |

Fails quietly to sample content if the API is unreachable. Override with `?api=https://your-host:8000`.

The public product site is served at `/`. Authenticated application surfaces are separate entries:

- `/workspace.html` — investigation workspace
- `/knowledge.html` — private knowledge operations
