#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${1:-}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 2
fi

if [[ -z "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  echo "usage: DATABASE_URL=... scripts/restore-postgres.sh /backups/harness-YYYYMMDD.sql.gz" >&2
  exit 2
fi

if [[ "${CONFIRM_RESTORE:-}" != "restore-harness-postgres" ]]; then
  echo "set CONFIRM_RESTORE=restore-harness-postgres to restore ${BACKUP_FILE}" >&2
  exit 2
fi

gunzip -c "${BACKUP_FILE}" | psql "${DATABASE_URL}"
echo "restored ${BACKUP_FILE}"
