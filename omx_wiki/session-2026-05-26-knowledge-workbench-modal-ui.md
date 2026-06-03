# Knowledge Workbench Modal UI

Category: `session-log`

Tags: `agent-console`, `knowledge`, `ui`, `modal`, `browser-smoke`, `chinese-first`

## Summary

The standalone `/knowledge` workbench now uses modal dialogs for configuration flows instead of rendering long forms inline on the page.

This keeps the main workbench focused on:

- overview metrics and filters;
- source list with scope, health, provider, and validation badges;
- selected-source summary and lifecycle actions;
- document/version summaries.

## Delivered

- `KnowledgeManagementPanel` source creation now exposes compact `本地文档` and `外部 API` buttons in the source list header.
- Local source creation and API connector configuration open a shared modal dialog.
- Source name/description editing opens an edit modal instead of inline inputs.
- Add-document and reingest-version forms open modal dialogs from compact action buttons.
- The existing Knowledge/RAG API payloads, connector presets, required-field validation, and lifecycle behavior remain unchanged.
- External API connector submission now uses `保存配置` / `保存中` wording instead of document-indexing wording.
- Connector source creation has a 12s frontend timeout that surfaces `请求超时` and releases the disabled button if the backend stalls; local text/file source creation is not capped by this timeout.

## Validation

```text
cd apps/agent-console && npm test -- KnowledgeManagementPanel.render.test.tsx KnowledgePage.test.tsx
2 files / 10 tests passed

cd apps/agent-console && npm test -- api.test.ts ConsoleShell.render.test.tsx Knowledge
4 files / 18 tests passed

cd apps/agent-console && npm run lint -- --pretty false
passed

cd apps/agent-console && npm run build
passed, with existing Vite chunk-size warning

cd services/api-server && uv run pytest tests/test_knowledge_connectors.py tests/test_knowledge_rag.py -q
57 passed

cd services/api-server && uv run ruff check app tests
passed

curl --noproxy '*' -sS -m 5 -I http://127.0.0.1:5173/knowledge
HTTP 200

curl --noproxy '*' -sS -m 5 http://127.0.0.1:8000/health
{"status":"ok","service":"api-server"}

Live connector save smoke
POST /api/agents/default/knowledge/sources with a temporary Dify connector returned immediately with connector_config_only=true and retrieval_eligible=false; POST /archive cleaned up the temporary source.

Playwright DOM check at http://127.0.0.1:5173/knowledge
before opening dialog: overflow=0, no inline `外部 API 地址` input, no inline `密钥引用` input, dialogCount=0
after clicking `外部 API`: overflow=0, dialog=`新增外部 API 接入`, endpoint and secret-ref inputs visible in the modal, console errors=[]

git diff --check
passed
```

## Notes

- Vitest still emits existing React `act(...)` warnings around `KnowledgeManagementPanel` async updates; tests pass with exit code 0.
- Screenshot artifact from the Playwright check: `/tmp/knowledge-modal-ui.png`.
- The original stuck state was reproduced as a local runtime problem: the old `127.0.0.1:8000` API process stopped responding, then disappeared; Vite stayed up on `127.0.0.1:5173` and proxied `/api` to a failed backend. The service was restarted with `uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`.
