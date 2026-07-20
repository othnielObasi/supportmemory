# Vultr Deployment

TraceMemory can run on a Vultr Compute instance using Docker Compose.

## Services

- `console` — React UI on port `3000`
- `api` — FastAPI runtime on port `8000`
- `postgres` — durable runtime store
- `recovery-worker` — restores interrupted runs
- `mock-tools` — keyless MCP-style demo tools

## Deploy

```bash
cd infra/vultr
bash deploy.sh
```

or:

```bash
docker compose up -d --build
```

## Environment

```env
DEMO_MODE=true
DEFAULT_MODEL_GATEWAY=mock
FRONTEND_ORIGIN=http://localhost:3000
```

Use live `MCP_GATEWAY_URL` and model provider keys only when moving beyond the keyless judge demo.
