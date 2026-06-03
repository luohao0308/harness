#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${HARNESS_MIGRATION_PREFLIGHT_CONTAINER:-harness-pg-migration-preflight}"
POSTGRES_PORT="${HARNESS_MIGRATION_PREFLIGHT_PORT:-15432}"
POSTGRES_PASSWORD="${HARNESS_MIGRATION_PREFLIGHT_PASSWORD:-t}"
PREFLIGHT_MODE="${HARNESS_MIGRATION_PREFLIGHT_MODE:-auto}"
PGDATA_DIR=""

run_alembic() {
  local database_url="$1"
  (
    cd services/api-server
    DATABASE_URL="${database_url}" .venv/bin/python -m alembic upgrade head
  )
}

cleanup() {
  docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  if [[ -n "${PGDATA_DIR}" && -d "${PGDATA_DIR}" ]]; then
    pg_ctl -D "${PGDATA_DIR}" -m fast stop >/dev/null 2>&1 || true
    rm -rf "${PGDATA_DIR}"
  fi
}

cleanup
trap cleanup EXIT

docker_available() {
  command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1
}

run_with_docker() {
  local database_url="postgresql+psycopg://postgres:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/postgres"

  docker run --rm \
    -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
    -p "${POSTGRES_PORT}:5432" \
    -d \
    --name "${CONTAINER_NAME}" \
    postgres:16 >/dev/null

  for _ in $(seq 1 30); do
    if docker exec "${CONTAINER_NAME}" pg_isready -U postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  docker exec "${CONTAINER_NAME}" pg_isready -U postgres >/dev/null
  run_alembic "${database_url}"
}

run_with_local_postgres() {
  for binary in initdb pg_ctl pg_isready; do
    command -v "${binary}" >/dev/null 2>&1 || {
      echo "Missing ${binary}; install PostgreSQL or run with Docker available." >&2
      return 1
    }
  done

  PGDATA_DIR="$(mktemp -d "${TMPDIR:-/tmp}/harness-pg-migration-preflight.XXXXXX")"
  LC_ALL=en_US.UTF-8 LANG=en_US.UTF-8 \
    initdb -D "${PGDATA_DIR}" -A trust -U postgres -E UTF8 --locale=en_US.UTF-8 >/dev/null
  pg_ctl -D "${PGDATA_DIR}" -o "-p ${POSTGRES_PORT} -c listen_addresses=127.0.0.1" -w start >/dev/null

  for _ in $(seq 1 30); do
    if pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT}" -U postgres >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done

  pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT}" -U postgres >/dev/null
  run_alembic "postgresql+psycopg://postgres@127.0.0.1:${POSTGRES_PORT}/postgres"
}

case "${PREFLIGHT_MODE}" in
  docker)
    run_with_docker
    ;;
  local)
    run_with_local_postgres
    ;;
  auto)
    if docker_available; then
      run_with_docker
    else
      echo "Docker daemon unavailable; falling back to local PostgreSQL binaries." >&2
      run_with_local_postgres
    fi
    ;;
  *)
    echo "Unsupported HARNESS_MIGRATION_PREFLIGHT_MODE=${PREFLIGHT_MODE}; expected auto, docker, or local." >&2
    exit 2
    ;;
esac
