#!/usr/bin/env bash
# Deploy TraceMemory to an Alibaba Cloud ECS instance.
# Run this on the ECS instance itself (via SSH), or adapt as an ECS
# instance user-data / cloud-init script.
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is required. Install docker-compose-plugin and retry." >&2
  exit 1
fi

cp -n .env.example .env || true

echo "Set QWEN_API_KEY and ALIBABA_OSS_BUCKET (+ access keys) in .env before starting for live mode."
echo "Deploying on Alibaba Cloud ECS..."

docker compose up -d --build

echo "TraceMemory is starting on Alibaba Cloud ECS."
echo "API:     http://$(curl -s ifconfig.me):8000/health"
echo "Console: http://$(curl -s ifconfig.me):3000"
