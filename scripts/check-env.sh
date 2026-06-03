#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_files=(
  ".env.example"
  "services/api-server/.env.example"
  "apps/web-site/.env.example"
  "apps/agent-console/.env.example"
  "deploy/docker-compose/.env.example"
)

required_root_vars=(
  "APP_ENV"
  "APP_BASE_URL"
  "CONSOLE_BASE_URL"
  "API_BASE_URL"
  "DATABASE_URL"
  "REDIS_URL"
  "MODEL_GATEWAY_BASE_URL"
  "MODEL_GATEWAY_API_KEY"
  "DOCKER_HOST"
  "AUTH_JWT_SECRET"
  "AUTH_PUBLIC_REGISTRATION_ENABLED"
  "HARNESS_SECRET_ENCRYPTION_KEY"
)

for file in "${required_files[@]}"; do
  test -f "$ROOT_DIR/$file"
done

for key in "${required_root_vars[@]}"; do
  grep -Eq "^${key}=" "$ROOT_DIR/.env.example"
done

echo "environment checks passed"
