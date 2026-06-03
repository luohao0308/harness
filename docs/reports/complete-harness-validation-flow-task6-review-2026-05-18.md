# Complete Harness Validation Flow — Task 6 Review

## Scope

Release integration, docs, smoke scripts, and final evidence checklist for the OMX-independent release gate.

## Candidate files

- `scripts/validate-harness-flow.sh`
- `scripts/check-release-spine-evidence.py`
- `docs/runbooks/deployment.md`
- `docs/runbooks/troubleshooting.md`
- `docs/TECHNICAL-IMPLEMENTATION-PROGRESS.md`
- `docs/task-progress.md`
- `docs/human/10-task-progress.md`

## Hazards / shared-file warnings

- The release smoke evidence JSON path must match between the runbook and `scripts/validate-harness-flow.sh`; otherwise handoff operators will write evidence to one path and validate another.
- `docs/task-progress.md`, `docs/human/10-task-progress.md`, and `docs/ai/task-progress.yaml` are coupled progress mirrors and should not drift.
- `docs/runbooks/deployment.md` is shared release-facing documentation; keep the path wording aligned with the smoke script so local and CI handoffs use the same artifact path.

## Recommended minimal slice

- Keep the release gate OMX-independent.
- Use the report-dir-scoped Phase 0b evidence paths as the canonical handoff location.
- Leave the smoke logic unchanged unless the path contract or evidence schema changes.
- Refresh only the release runbook wording and this report artifact for the current release-integration pass.

## Verification

- `python3 scripts/validate-docs.py` — PASS
- `cd apps/agent-console && npm run e2e:smoke:release` — existing release smoke entrypoint remains the canonical browser gate
- `python3 scripts/check-release-spine-evidence.py --write-template .omx/reports/complete-harness-validation-flow/phase0b-release-spine-evidence.template.json` — canonical template path referenced by the runbook

## Notes

- This pass only closes the documentation/path-consistency hazard.
- Phase 0b completion still requires a real evidence JSON with package staging, Agent creation/attachment, usable connector sync, Workspace orchestration/subagent run, Run Detail evidence, and token/cost panel.
