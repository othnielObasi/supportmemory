#!/usr/bin/env bash
set -euo pipefail

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is required. Install docker-compose-plugin and retry." >&2
  exit 1
fi

cp -n .env.example .env || true
docker compose up -d --build

echo "TraceMemory is starting."
echo "API:     http://localhost:8000/health"
echo "Console: http://localhost:5174"
echo "Demo:    http://localhost:5173"
