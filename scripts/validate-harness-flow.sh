#!/usr/bin/env bash
# Complete Harness Validation Flow — orchestration script
#
# Usage:
#   ./scripts/validate-harness-flow.sh [--local-dev | --full-infra]
#
# Layers:
#   L0: Static/unit/build/docs gates
#   L1: Backend canonical Harness-chain smoke
#   L2: Mocked browser product-perception tests
#   L3: Live browser validation (requires running backend + HARNESS_E2E_RUN_ID)
#   L4: UI deep-link and state coherence (covered by L2 run-detail tests)
#   L5: Evidence capture
#
# Exit codes:
#   0 — all layers passed
#   1 — one or more layers failed

set -euo pipefail

REPORT_DIR=".omx/reports/complete-harness-validation-flow"
PROFILE="${1:---local-dev}"
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%SZ")

mkdir -p "$REPORT_DIR"

echo "=== Complete Harness Validation Flow ==="
echo "Profile: $PROFILE"
echo "Timestamp: $TIMESTAMP"
echo ""

FAILED=0

# ---------------------------------------------------------------------------
# L0: Static / Unit / Build
# ---------------------------------------------------------------------------
echo "--- L0: Static / Unit / Build ---"

echo "[L0] Frontend tests..."
(cd apps/agent-console && npm test) > "$REPORT_DIR/l0-frontend-test.txt" 2>&1 || { echo "FAIL: npm test"; FAILED=1; }

echo "[L0] Frontend lint (tsc)..."
(cd apps/agent-console && npm run lint) > "$REPORT_DIR/l0-frontend-lint.txt" 2>&1 || { echo "FAIL: npm run lint"; FAILED=1; }

echo "[L0] Frontend build..."
(cd apps/agent-console && npm run build) > "$REPORT_DIR/l0-frontend-build.txt" 2>&1 || { echo "FAIL: npm run build"; FAILED=1; }

echo "[L0] Docs validation..."
python3 scripts/validate-docs.py > "$REPORT_DIR/l0-docs-validation.txt" 2>&1 || { echo "FAIL: validate-docs.py"; FAILED=1; }

echo "[L0] Whitespace check..."
git diff --check > "$REPORT_DIR/l0-whitespace.txt" 2>&1 || { echo "FAIL: git diff --check"; FAILED=1; }

echo ""

# ---------------------------------------------------------------------------
# L1: Backend Canonical Harness Chain
# ---------------------------------------------------------------------------
echo "--- L1: Backend Canonical Harness Chain ---"

echo "[L1] Running canonical smoke..."
if python3 scripts/smoke-test-agent-run.py > "$REPORT_DIR/backend-smoke.txt" 2>&1; then
  echo "[L1] PASS"
  # Extract evidence JSON
  grep -o 'EVIDENCE {.*}' "$REPORT_DIR/backend-smoke.txt" | sed 's/EVIDENCE //' > "$REPORT_DIR/evidence.json" 2>/dev/null || true
  if [ -f "$REPORT_DIR/evidence.json" ] && [ -s "$REPORT_DIR/evidence.json" ]; then
    HARNESS_E2E_RUN_ID=$(python3 -c "import json,sys; d=json.load(open('$REPORT_DIR/evidence.json')); print(d.get('run_id',''))" 2>/dev/null || echo "")
    export HARNESS_E2E_RUN_ID
    echo "  Evidence run_id: $HARNESS_E2E_RUN_ID"
  fi
else
  echo "[L1] FAIL: canonical smoke failed"
  FAILED=1
fi

echo ""

# ---------------------------------------------------------------------------
# L2: Mocked Browser Product Perception
# ---------------------------------------------------------------------------
echo "--- L2: Mocked Browser Tests ---"

echo "[L2] Running e2e:smoke..."
(cd apps/agent-console && npm run e2e:smoke) > "$REPORT_DIR/l2-mocked-browser.txt" 2>&1 || { echo "FAIL: e2e:smoke"; FAILED=1; }

echo ""

# ---------------------------------------------------------------------------
# L3: Live Browser Validation
# ---------------------------------------------------------------------------
echo "--- L3: Live Browser Validation ---"

if [ -n "${HARNESS_E2E_RUN_ID:-}" ]; then
  echo "[L3] Running e2e:live with RUN_ID=$HARNESS_E2E_RUN_ID..."
  (cd apps/agent-console && HARNESS_E2E_RUN_ID="$HARNESS_E2E_RUN_ID" npm run e2e:live) > "$REPORT_DIR/l3-live-browser.txt" 2>&1 || { echo "FAIL: e2e:live"; FAILED=1; }
else
  echo "[L3] SKIP: No HARNESS_E2E_RUN_ID available (backend smoke may have failed)"
  echo "SKIPPED: No run_id from L1" > "$REPORT_DIR/l3-live-browser.txt"
fi

echo ""

# ---------------------------------------------------------------------------
# L5: Evidence Report
# ---------------------------------------------------------------------------
echo "--- L5: Evidence Report ---"

cat > "$REPORT_DIR/report-$TIMESTAMP.md" << EOF
# Complete Harness Validation Flow Report

- **Timestamp:** $TIMESTAMP
- **Profile:** $PROFILE
- **Run ID:** ${HARNESS_E2E_RUN_ID:-N/A}

## Layer Results

| Layer | Description | Status |
|-------|-------------|--------|
| L0 | Static/Unit/Build | $([ -f "$REPORT_DIR/l0-frontend-build.txt" ] && echo "See output" || echo "SKIP") |
| L1 | Backend Canonical | $([ -f "$REPORT_DIR/evidence.json" ] && [ -s "$REPORT_DIR/evidence.json" ] && echo "PASS" || echo "FAIL/SKIP") |
| L2 | Mocked Browser | $([ -f "$REPORT_DIR/l2-mocked-browser.txt" ] && echo "See output" || echo "SKIP") |
| L3 | Live Browser | $([ -n "${HARNESS_E2E_RUN_ID:-}" ] && echo "See output" || echo "SKIP (no run_id)") |
| L4 | Deep-link Coherence | Covered by L2 run-detail tests |
| L5 | Evidence Capture | This report |

## Profile Notes

$(if [ "$PROFILE" = "--full-infra" ]; then
  echo "Full-infra profile: Tempo and Loki are expected to be running."
  echo "This evidence can be used to close the complete validation goal."
else
  echo "Local-dev profile: Tempo/Loki may be unavailable."
  echo "This evidence is PARTIAL and must not be used to mark complete progress."
fi)

## Evidence Keys

$(if [ -f "$REPORT_DIR/evidence.json" ] && [ -s "$REPORT_DIR/evidence.json" ]; then
  cat "$REPORT_DIR/evidence.json"
else
  echo "No evidence JSON captured."
fi)
EOF

echo "[L5] Report written to $REPORT_DIR/report-$TIMESTAMP.md"
echo ""

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
if [ $FAILED -eq 0 ]; then
  echo "=== ALL LAYERS PASSED ==="
  exit 0
else
  echo "=== SOME LAYERS FAILED ==="
  exit 1
fi
