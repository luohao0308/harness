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

required_server_vars=(
  "APP_ENV"
  "API_BASE_URL"
  "DATABASE_URL"
  "REDIS_URL"
  "AI_PROVIDER_PROTOCOL"
  "AI_PROVIDER_BASE_URL"
  "AI_PROVIDER_MODEL"
  "AI_PROVIDER_MODELS"
  "AI_PROVIDER_NAME"
  "AI_PROVIDER_API_KEY"
  "AUTH_JWT_SECRET"
  "AUTH_PUBLIC_REGISTRATION_ENABLED"
  "HARNESS_SECRET_ENCRYPTION_KEY"
)

required_root_only_vars=(
  "APP_BASE_URL"
  "CONSOLE_BASE_URL"
  "DOCKER_HOST"
)

for file in "${required_files[@]}"; do
  test -f "$ROOT_DIR/$file"
done

for template in ".env.example" "services/api-server/.env.example" "deploy/docker-compose/.env.example"; do
  for key in "${required_server_vars[@]}"; do
    grep -Eq "^${key}=" "$ROOT_DIR/$template"
  done
  # The checked-in templates document the server-only key but never contain one.
  grep -Eq "^AI_PROVIDER_API_KEY=$" "$ROOT_DIR/$template"
done

for key in "${required_root_only_vars[@]}"; do
  grep -Eq "^${key}=" "$ROOT_DIR/.env.example"
done

if rg -q '^AI_PROVIDER_API_KEY=' "$ROOT_DIR/apps/agent-console" "$ROOT_DIR/apps/web-site"; then
  echo "AI_PROVIDER_API_KEY must not appear in browser environment templates" >&2
  exit 1
fi

echo "environment checks passed"
