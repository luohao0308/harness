# Workspace Viewport and Subagent Invocation Hardening

Category: `session-log`

Tags: `workspace`, `agent-console`, `browser-smoke`, `playwright`, `subagents`, `orchestration`, `viewport`

## Summary

Fixed two live Workspace issues reported on `http://127.0.0.1:15173/agents/default/workspace`: the page required outer document scrolling on open at compact desktop height, and Chinese requests to call a subagent could miss orchestration routing and fall back to local-knowledge behavior.

## Implemented

- Bounded the Agent Console shell to the viewport with `h-screen`, `min-h-0`, and route-aware overflow rules so Workspace and Team routes do not create document-level scroll.
- Bounded the Workspace page itself with `h-full min-h-0 overflow-hidden`, preserving internal chat scrolling instead of scrolling the entire page.
- Hid collapsed sidebar labels with `hidden` instead of invisible absolute text, preventing collapsed navigation text from increasing document scroll height.
- Added frontend orchestration inference for explicit Chinese subagent or multi-agent requests and for follow-up invocation wording when recent chat path context already mentions subagents.
- Added backend normalization for NFKC text, spacing, Chinese subagent synonyms, multi-agent wording, and follow-up invocation phrases such as `你现在调用一下`.

## Validation

- `cd apps/agent-console && npm test -- useChatStream.test.tsx --run` -> `9 passed`.
- `cd services/api-server && .venv/bin/python -m pytest tests/test_agents.py -k "force_subagent or auto_subagent" -q` -> `3 passed, 61 deselected`.
- `cd apps/agent-console && npm run lint -- --pretty false` -> passed.
- `cd services/api-server && .venv/bin/python -m ruff check app/api/agents/_workspace_chat_helpers.py tests/test_agents.py` -> passed.
- `cd apps/agent-console && HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test e2e/agent-workspace.smoke.spec.ts --project=chromium` -> `4 passed`.
- Live `15173` DOM metrics at `1640x768`: `rootScrollHeight=768`, `rootClientHeight=768`, `bodyScrollHeight=768`, `bodyClientHeight=768`, `noDocumentVerticalOverflow=true`, and `noHorizontalOverflow=true`.
- `cd apps/agent-console && npm run build` -> passed.
- `python3 scripts/validate-docs.py` -> passed.
- `git diff --check` -> passed.

## Notes

- An initial broad Playwright script invocation failed before app assertions because `127.0.0.1:5177` was not listening. After starting Vite manually and running the targeted Workspace spec with `HARNESS_PLAYWRIGHT_EXTERNAL_SERVER=1`, the Workspace browser suite passed.
- This slice keeps the existing Workspace product constraint intact: the first viewport remains chat-first, with no dashboard takeover and no outer page scroll.
