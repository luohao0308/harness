# Phase 1.1: IPC Bridge Foundation (TDD)

## Summary

Phase 1.1 establishes the Electron IPC bridge foundation using strict Test-Driven Development (TDD) methodology. This phase implements secure communication between the Electron renderer process and the backend API server, with Server-Sent Events (SSE) streaming support for real-time agent updates.

## Status

**✅ COMPLETED** - 2026-06-25

## Goals

- Implement secure IPC bridge between Electron renderer and main process
- Expose type-safe APIs through contextBridge with contextIsolation=true
- Handle agent operations: bind conversation, send message, get workspace, list connections
- Handle task operations: get, cancel, list with filtering
- Implement SSE streaming with exponential backoff retry logic
- Achieve minimum 80% test coverage using TDD methodology
- Follow DRY principle and extract shared utilities

## DoD Commit Hygiene

- Plan for N atomic commits that match the PRD work items, with a tolerance of +/-2 when closely related cleanup is safer to merge together.
- Each commit must leave the touched backend/frontend surface buildable and its relevant targeted tests passing.
- Commit messages must follow the repository Lore protocol, including `Scope-risk:` and `Tested:` trailers when they add decision context.

## TDD Workflow

All development followed strict RED → GREEN → REFACTOR cycle:

1. **RED Phase**: Write failing test first
2. **GREEN Phase**: Write minimal implementation to pass test
3. **REFACTOR Phase**: Optimize code under test protection

## Architecture

### Trust Boundary

- **Renderer Process**: Untrusted, runs user-facing React app with contextIsolation=true
- **Main Process**: Trusted mediator between renderer and backend API
- **Backend API**: Single source of truth for all agent/task data

### Communication Flow

```
Renderer Process (contextBridge API)
    ↓ IPC
Main Process (agent-service.ts, task-service.ts, sse-bridge.ts)
    ↓ HTTP/SSE
Backend API Server
```

## Implementation

### Core Modules

#### 1. Preload Script ([src/preload.ts](../../apps/desktop-app/src/preload.ts))
- Exposes type-safe APIs through `contextBridge.exposeInMainWorld()`
- TypeScript interfaces ensure compile-time safety
- **Coverage**: 100% statement, 100% branch, 100% function

#### 2. Agent Service ([src/services/agent-service.ts](../../apps/desktop-app/src/services/agent-service.ts))
- `agent:bind-conversation` - Create/bind agent conversation session
- `agent:send-message` - Send user message to agent
- `agent:get-workspace` - Retrieve agent run workspace with selectors
- `agent:list-connections` - List all local agent connections
- Uses shared `apiRequest()` and `buildQueryString()` utilities
- **Coverage**: 100% statement, 100% branch, 100% function

#### 3. Task Service ([src/services/task-service.ts](../../apps/desktop-app/src/services/task-service.ts))
- `task:get` - Get single task by ID
- `task:cancel` - Cancel running task
- `task:list` - List tasks with optional status filter
- Uses shared `apiRequest()` and `buildQueryString()` utilities
- **Coverage**: 100% statement, 100% branch, 100% function

#### 4. SSE Bridge ([src/services/sse-bridge.ts](../../apps/desktop-app/src/services/sse-bridge.ts))
- Real-time event streaming using EventSource
- Exponential backoff retry: delay = 2^(n-1) * 1000ms, max 30s
- Connection status broadcasting to all renderer windows
- Event parsing and forwarding with sequence tracking
- Uses shared `getApiBaseUrl()` and `getAuthToken()` utilities
- **Coverage**: 98.09% statement, 86.95% branch, 100% function

#### 5. Shared API Client ([src/shared/api-client.ts](../../apps/desktop-app/src/shared/api-client.ts))
- Centralized HTTP client utilities following DRY principle
- `getApiBaseUrl()` - Get API base URL from env or default
- `getAuthToken()` - Get auth token from env
- `apiRequest<T>()` - Generic HTTP request with auth and error handling
- `buildQueryString()` - Build URL query strings from params
- **Coverage**: 100% statement, 100% branch, 100% function

### Key Patterns

#### Exponential Backoff Retry
```typescript
function calculateRetryDelay(attemptNumber: number, maxDelayMs: number): number {
  const exponentialDelay = Math.pow(2, attemptNumber - 1) * 1000
  return Math.min(exponentialDelay, maxDelayMs)
}
```

#### Query String Building
```typescript
export function buildQueryString(params: Record<string, string | undefined>): string {
  const searchParams = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      searchParams.set(key, value)
    }
  }
  const queryString = searchParams.toString()
  return queryString ? `?${queryString}` : ''
}
```

#### Generic API Request
```typescript
export async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${getApiBaseUrl()}${endpoint}`
  const token = getAuthToken()

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token && { Authorization: `Bearer ${token}` }),
      ...options.headers,
    },
  })

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status} ${response.statusText}`
    )
  }

  return response.json()
}
```

## Test Coverage

### Final Coverage Report (92 tests passing)

```
File               | % Stmts | % Branch | % Funcs | % Lines
-------------------|---------|----------|---------|----------
All files          |   99.44 |    95.94 |     100 |   99.44
 src               |     100 |      100 |     100 |     100
  main.ts          |     100 |      100 |     100 |     100
  preload.ts       |     100 |      100 |     100 |     100
 src/config        |     100 |      100 |     100 |     100
  app.ts           |     100 |      100 |     100 |     100
 src/services      |   98.94 |     90.9 |     100 |   98.94
  agent-service.ts |     100 |      100 |     100 |     100
  sse-bridge.ts    |   98.09 |    86.95 |     100 |   98.09
  task-service.ts  |     100 |      100 |     100 |     100
 src/shared        |     100 |      100 |     100 |     100
  api-client.ts    |     100 |      100 |     100 |     100
```

### Test Suites

1. **[preload.test.ts](../../apps/desktop-app/src/__tests__/preload.test.ts)** (11 tests)
   - Tests all contextBridge API exposure
   - Verifies type-safe IPC method registration

2. **[agent-ipc.test.ts](../../apps/desktop-app/src/__tests__/agent-ipc.test.ts)** (13 tests)
   - Tests all agent IPC handlers
   - Covers auth token inclusion, error handling, query string building

3. **[task-ipc.test.ts](../../apps/desktop-app/src/__tests__/task-ipc.test.ts)** (16 tests)
   - Tests all task IPC handlers
   - Covers filtering, cancellation, error handling

4. **[sse-bridge.test.ts](../../apps/desktop-app/src/__tests__/sse-bridge.test.ts)** (12 tests)
   - Tests SSE connection lifecycle
   - Covers retry logic, event parsing, status broadcasting

5. **[api-client.test.ts](../../apps/desktop-app/src/shared/__tests__/api-client.test.ts)** (13 tests)
   - Tests shared API client utilities
   - Covers all functions with default/custom scenarios

6. **[main.test.ts](../../apps/desktop-app/src/__tests__/main.test.ts)** (5 tests)
   - Tests main process initialization

7. **[lifecycle.test.ts](../../apps/desktop-app/src/__tests__/lifecycle.test.ts)** (4 tests)
   - Tests window lifecycle events

8. **[hot-reload.test.ts](../../apps/desktop-app/src/__tests__/hot-reload.test.ts)** (4 tests)
   - Tests development hot reload

9. **[production.test.ts](../../apps/desktop-app/src/__tests__/production.test.ts)** (3 tests)
   - Tests production build configuration

10. **[app.test.ts](../../apps/desktop-app/src/config/__tests__/app.test.ts)** (3 tests)
    - Tests application configuration

11. **[e2e.test.ts](../../apps/desktop-app/src/__tests__/e2e.test.ts)** (5 tests)
    - End-to-end integration tests

12. **[integration.test.ts](../../apps/desktop-app/src/__tests__/integration.test.ts)** (3 tests)
    - React SPA integration tests

## Refactoring Achievements

### DRY Principle Applied

Identified and eliminated code duplication across three service files:
- Extracted `DEFAULT_API_BASE_URL` and `CONTENT_TYPE_JSON` constants
- Created `getApiBaseUrl()` and `getAuthToken()` utilities
- Created `apiRequest<T>()` generic HTTP client
- Created `buildQueryString()` query parameter utility
- Created `calculateRetryDelay()` exponential backoff utility

**Before**: Each service file duplicated 50+ lines of boilerplate
**After**: All services import from shared [src/shared/api-client.ts](../../apps/desktop-app/src/shared/api-client.ts)

### Code Quality Improvements

- Extracted magic numbers to named constants
- Created focused utility functions with single responsibility
- Eliminated code duplication following DRY principle
- Maintained 100% test coverage for all extracted utilities
- Improved maintainability and testability

## Security Considerations

### Authentication
- Bearer token from `process.env.AUTH_TOKEN`
- Included in all HTTP requests via Authorization header
- SSE auth via `access_token` query parameter

### Environment Variables
- `API_BASE_URL` - Backend API server URL (default: http://localhost:8000)
- `AUTH_TOKEN` - Bearer token for API authentication

### Context Isolation
- `contextIsolation=true` enforced in BrowserWindow
- No direct Node.js API exposure to renderer
- All APIs explicitly registered through contextBridge

## Non-Goals (Phase 1.1)

- Host tool approval panel (belongs to V3)
- Unified ChatSurface within Workspace (belongs to V2)
- Cancel/retry complete lifecycle (belongs to V3)
- Raw env/secret upload (security boundary)

## Future Work

### Phase 1.2: Renderer Integration
- Connect React UI to IPC APIs
- Implement agent conversation UI
- Display task list and status
- Show SSE connection status

### Phase 1.3: Permission System
- Implement host tool approval UI
- Add pending change review
- Implement cancel/retry flows

## References

- [prd-local-agent-bridge-conversation-v1.md](./prd-local-agent-bridge-conversation-v1.md) - Parent PRD
- [apps/desktop-app/package.json](../../apps/desktop-app/package.json) - Test scripts and dependencies
- [apps/desktop-app/vitest.config.ts](../../apps/desktop-app/vitest.config.ts) - Test configuration

## Lessons Learned

1. **TDD methodology pays off**: Writing tests first caught design issues early
2. **DRY principle is critical**: Code duplication was identified after GREEN phase and eliminated in REFACTOR phase
3. **High test coverage enables fearless refactoring**: 99%+ coverage allowed aggressive DRY refactoring without regression
4. **Shared utilities improve maintainability**: Centralizing common code in `src/shared/api-client.ts` reduced duplication by 150+ lines
5. **Exponential backoff is essential**: SSE retry logic handles network instability gracefully
6. **Type safety prevents runtime errors**: TypeScript interfaces caught parameter mismatches at compile time
