#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="${1:-$ROOT_DIR/apps/agent-console/dist}"
ASSET_DIR="$DIST_DIR/assets"

if [[ ! -d "$ASSET_DIR" ]]; then
  echo "missing asset directory: $ASSET_DIR" >&2
  exit 1
fi

: "${S3_BUCKET:?S3_BUCKET required}"
AWS_REGION="${AWS_REGION:-us-east-1}"
S3_PREFIX="${S3_PREFIX:-assets}"
CACHE_CONTROL="${CACHE_CONTROL:-public, max-age=31536000, immutable}"

aws s3 sync "$ASSET_DIR" "s3://$S3_BUCKET/$S3_PREFIX/" \
  --region "$AWS_REGION" \
  --delete \
  --cache-control "$CACHE_CONTROL"

if [[ -n "${CLOUDFRONT_DISTRIBUTION_ID:-}" ]]; then
  aws cloudfront create-invalidation \
    --distribution-id "$CLOUDFRONT_DISTRIBUTION_ID" \
    --paths "/$S3_PREFIX/*" \
    --region "$AWS_REGION" >/dev/null
fi

echo "uploaded $ASSET_DIR to s3://$S3_BUCKET/$S3_PREFIX/"
