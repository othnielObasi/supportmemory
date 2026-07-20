# Deploy TraceMemory on Vultr

This hackathon build is designed to run as a Docker Compose stack on a Vultr Compute instance.

## Stack

- `api` — FastAPI TraceMemory runtime API
- `console` — TraceMemory UI
- `ticket-agent-demo` — local recovery demo surface
- `postgres` — durable runtime records
- `recovery-worker` — simulated recovery worker loop

## Quick deployment

1. Create a Vultr Ubuntu Compute instance.
2. Open ports `80`, `443`, `8000`, `5173`, and `5174` as needed for judging.
3. SSH into the instance.
4. Run:

```bash
git clone https://github.com/<your-org>/tracememory.git
cd tracememory
cp .env.example .env
docker compose up -d --build
```

## Demo URLs

- Console: `http://<server-ip>:5174`
- Agent demo: `http://<server-ip>:5173`
- API health: `http://<server-ip>:8000/health`
- One-click demo endpoint: `POST http://<server-ip>:8000/api/demo/failure-recovery`

## Production hardening after judging

- Put Caddy or Nginx in front of API/UI.
- Use managed PostgreSQL if available.
- Enable TLS.
- Set `AUTH_REQUIRED=true`.
- Rotate API keys and signing secrets.
