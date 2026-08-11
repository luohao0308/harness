# Troubleshooting Guide

This file is the operator entry point for deployment and runtime diagnosis
outside the Console. The canonical searchable case catalog is stored at
`apps/agent-console/public/help/troubleshooting.md` and is rendered in the app
at `/help/troubleshooting`.

## Fast Triage

1. Validate the compose file before starting services:

   ```bash
   docker compose -f compose.production.yml config
   ```

2. Check dependency health in order: Postgres, Redis, API readiness, proxy, then
   Console assets.

3. Use the Run Detail page for product workflow failures. It contains events,
   model calls, tool calls, sandbox state, Specialist output, Eval evidence, and
   trace links.

4. Use `/settings/frontend-errors` for browser-side failures and organization
   audit events for auth, RBAC, retention, export, deletion, and capability
   lifecycle failures.

## Case Catalog

The in-app catalog currently covers 51 cases across deployment, auth, model
providers, knowledge/RAG, Agent Runs, tools, sandboxes, MCP, Eval, Specialists,
observability, retention, CDN assets, load testing, cache behavior, and cursor
pagination.

Keep the root guide short so operators know where to start, and keep the full
case list inside `public/help` so Console search and documentation validation
share one source.
