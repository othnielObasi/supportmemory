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

Canonical file:

- `HACKATHON_UI.html`

Synced copies (keep in sync when editing):

- `apps/console/public/hackathon-ui.html` (hero image path: `/assets/hero-supportmemory.jpg`)
- `docs/assets/supportmemory-ui.html`

Hero asset:

- `assets/hero-supportmemory.jpg`
- `apps/console/public/assets/hero-supportmemory.jpg`

### Design system

- Accent: amber `#f59e0b` → `#ff5226`
- Dark surfaces: `#0f1419`
- Light surfaces: `#fbf9f5` / `#f9fafb`
- Type: Instrument Serif (display) · Geist · Geist Mono
- Pages (client-side, no reload): Landing · Capabilities · Architecture · **Dashboard**

### Dashboard (priority surface)

Three columns + status bar matching Figma:

1. Investigations sidebar (`+ New investigation`, search, ticket list)
2. Ticket workspace (step rail, thread, composer)
3. Live Inspector (memory match, checkpoint, Qwen-Max metrics)

### Live data wiring

Shared client: `assets/supportmemory-wire.js` (console: `/supportmemory-wire.js`).

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

Console on port 3000 redirects to `/hackathon-ui.html`.
