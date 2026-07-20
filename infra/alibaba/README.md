# Alibaba Cloud Deployment

TraceMemory's backend runs on an Alibaba Cloud ECS instance using the same
Docker Compose stack as local development, plus a live connection to two
Alibaba Cloud services:

1. **Qwen Cloud (DashScope)** — the model gateway for reflection, curation,
   and drift-check reasoning. See `services/api/app/services/openai_compatible_gateway.py`
   (`provider="qwen"`) and `app/config.py` for the `QWEN_*` settings.
2. **Alibaba Cloud OSS (Object Storage Service)** — durable, tamper-evident
   archival of signed Execution Receipts, independent of the API container's
   lifecycle. See `services/api/app/services/alibaba_oss_service.py`, which
   uses Alibaba's official `oss2` SDK to write and read receipt objects.

## Provisioning

1. Create an ECS instance (Ubuntu 22.04+, `ecs.t6-c1m2.large` or similar is
   sufficient for the demo).
2. Create an OSS bucket in the same region and an AccessKey pair with OSS +
   ECS permissions (RAM sub-account recommended over the primary account key).
3. SSH in, clone the repo, then:

```bash
cd infra/alibaba
bash deploy.sh
```

4. Fill in `.env`:

```env
QWEN_API_KEY=sk-...
QWEN_MODEL=qwen-max
DEFAULT_MODEL_GATEWAY=qwen
ALIBABA_ACCESS_KEY_ID=...
ALIBABA_ACCESS_KEY_SECRET=...
ALIBABA_OSS_BUCKET=tracememory-receipts
ALIBABA_OSS_REGION=oss-ap-southeast-1
ALIBABA_OSS_ENDPOINT=https://oss-ap-southeast-1.aliyuncs.com
```

5. Restart: `docker compose up -d --build`

## Proof of deployment

- Live URL: `http://<ecs-public-ip>:3000` (see `PUBLIC_DEMO_URL` in `.env`)
- Code proof (per submission rules): `services/api/app/services/alibaba_oss_service.py`
  — real `oss2` SDK calls, not a stub, wired into the live receipt endpoint at
  `GET /api/traces/{trace_id}/receipt`, which returns an `alibaba_oss_url`
  field once a receipt has been archived.
