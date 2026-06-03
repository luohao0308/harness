#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP="$(date +%Y%m%d)"
OUTPUT="${BACKUP_DIR}/harness-${TIMESTAMP}.sql.gz"

mkdir -p "${BACKUP_DIR}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

pg_dump "${DATABASE_URL}" | gzip -9 > "${OUTPUT}"
find "${BACKUP_DIR}" -name 'harness-*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete

if [[ -n "${RCLONE_REMOTE:-}" ]]; then
  rclone copy "${OUTPUT}" "${RCLONE_REMOTE%/}/"
fi

echo "${OUTPUT}"
