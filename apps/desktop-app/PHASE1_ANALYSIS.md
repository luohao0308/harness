# Phase 1 Analysis: Desktop Agent Execution & Task Management

## Current Web Implementation Summary

### 1. Agent Execution Flow

**API Functions** (from `apps/agent-console/src/features/tasks/api.ts`):

```typescript
// Bind local agent conversation to a connection
bindLocalAgentConversation(
  connectionId: string,
  payload: {
    agent_session_id?: string | null;
    title?: string | null;
    adapter_session_id?: string | null;
    resume_mode?: "native_resume" | "context_replay_new_session";
  }
): Promise<LocalAgentConversationBinding>

// Send message to local agent
sendLocalAgentMessage(
  bindingId: string,
  payload: LocalAgentSendMessagePayload
): Promise<LocalAgentSendMessageResponse>

// Get agent run workspace (includes run, events, subagents, tool_calls)
getAgentRunWorkspace(
  runId: string,
  selectors?: { retrieval_session_id?: string; prompt_manifest_id?: string }
): Promise<AgentRunWorkspace>
```

**Key Types**:

```typescript
type LocalAgentConversationBinding = {
  id: string;
  connection_id: string;
  agent_id: string;
  agent_session_id: string;
  adapter_session_id: string | null;
  resume_mode: string;
  status: string;
  created_at: string;
  updated_at: string;
}

type LocalAgentSendMessagePayload = {
  content: string;
  client_message_id: string;
  resume_of_client_message_id?: string | null;
  resume_of_user_message_id?: string | null;
  workspace_context_provided?: boolean;
  workspace_mode?: "chat" | "plan";
  model_provider?: string | null;
  model_name?: string | null;
  messages?: AgentChatStreamMessage[];
  // ... context fields
}

type LocalAgentSendMessageResponse = {
  bridge_task_id: string;
  run_id: string;
  agent_session_id: string;
  user_message_id: string;
  status: string;
}

type AgentRunWorkspace = {
  run: Task;
  plan: TaskPlan | null;
  events: AgentEvent[];
  knowledge_grounding: KnowledgeGrounding | null;
  context_assembly: ContextAssemblyManifest | null;
  token_optimization: Record<string, unknown>;
  subagents: Subagent[];
  tool_calls: ToolCall[];
  model_calls: ModelCall[];
  approvals: ToolApproval[];
  assignments: AgentAssignment[];
  handoffs: AgentHandoff[];
}
```

### 2. Real-time Streaming (SSE)

**SSE Client** (from `apps/agent-console/src/lib/sse-client.ts`):

```typescript
type SseClient = {
  close: () => void;
  retryNow: () => void;
}

createReconnectingSseClient<T>(
  urlFactory: (lastEventId: string | null) => string,
  options: {
    parse: (data: string) => T;
    onMessage: (event: T, raw: MessageEvent<string>) => void;
    onStatus?: (status: SseConnectionStatus) => void;
    maxRetryDelayMs?: number;
    maxAttemptsBeforeNotice?: number;
  }
): SseClient
```

**Stream URL** (from `apps/agent-console/src/features/tasks/api.ts`):
```typescript
taskEventReconnectStreamUrl(taskId: string, lastEventId: string | null): string
// Returns: /api/tasks/${taskId}/events/stream?access_token=...&after_sequence=...
```

**AgentWorkspacePage SSE Usage**:
- Creates SSE client for each agent run using `taskEventReconnectStreamUrl`
- Listens for `AgentEvent` types: `TOOL_APPROVAL_REQUESTED`, `LOCAL_AGENT_TOOL_REQUESTED`, content deltas
- Updates conversation nodes in real-time as events arrive
- Automatic reconnection with exponential backoff

### 3. Task Management

**Task Status** (from `apps/agent-console/src/features/tasks/api.ts`):
```typescript
type TaskStatus =
  | "CREATED"
  | "PLANNING"
  | "PLANNED"
  | "RUNNING"
  | "WAITING_SUBAGENTS"
  | "WAITING_APPROVAL"
  | "FAILED"
  | "COMPLETED"
  | "CANCELLED"

type Task = {
  id: string;
  agent_id?: string | null;
  title: string;
  goal: string;
  status: TaskStatus;
  model_provider: string;
  model_name: string;
  max_runtime_seconds: number;
  max_subagents: number;
  enable_sandbox: boolean;
  enable_network: boolean;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}
```

**Workspace State Management**:
- Uses zustand store (`useWorkspaceStore`) for conversation nodes
- Maintains `activeRunId`, `nodesById`, `rootNodeId`, `activeLeafId`
- Tracks local agent connections and bindings
- Manages pending assistant nodes during streaming

### 4. Local Agent Connections

**Connection Management**:
- Queries local connections every 3 seconds: `listLocalAgentConnections`
- Filters connections by `agent_id` and usability: `isUsableLocalAgentConnection`
- Maintains selected connection state: `selectedLocalConnectionId`
- Auto-syncs model selection with connection's model

## Desktop Integration Strategy

### Approach 1: Electron IPC Bridge (Recommended)

**Architecture**:
```
React UI (Renderer)
    ↓ (IPC)
Main Process (Electron)
    ↓ (HTTP/SSE)
Backend API Server
```

**Advantages**:
- Security: No direct HTTP from renderer (follows Electron best practices)
- Control: Main process can manage auth tokens, connections
- Offline-ready: Can intercept and queue requests for Phase 2
- Platform integration: Access to native features (notifications, system tray)

**IPC Channels**:
```typescript
// Main → Renderer
'agent:message-stream' // SSE events forwarded to renderer
'agent:connection-status' // Connection state updates
'task:status-change' // Task status updates

// Renderer → Main
'agent:send-message' // Send message to agent
'agent:bind-conversation' // Create conversation binding
'agent:get-workspace' // Fetch workspace data
'task:cancel' // Cancel task
'connection:list' // List connections
```

### Approach 2: Direct HTTP from Renderer (Simpler but less secure)

**Architecture**:
```
React UI (Renderer)
    ↓ (HTTP/SSE)
Backend API Server
```

**Advantages**:
- Simpler: Reuse existing web code
- Faster implementation: Minimal changes to existing React components

**Disadvantages**:
- Security: Requires `nodeIntegration=false` + `contextIsolation=true` maintained
- Harder offline sync: No main process interception
- Less native integration

## Recommended Implementation Plan

### Phase 1.1: IPC Bridge Foundation (RED → GREEN → REFACTOR) ✅ COMPLETED

**Status**: ✅ Completed on 2026-06-25

**Tests (RED)** ✅:
1. ✅ IPC channel registration tests (11 tests in `preload.test.ts`)
2. ✅ Agent message send via IPC tests (13 tests in `agent-ipc.test.ts`)
3. ✅ SSE → IPC forwarding tests (12 tests in `sse-bridge.test.ts`)
4. ✅ Error handling tests (network failures, auth errors) (16 tests in `task-ipc.test.ts`)

**Implementation (GREEN)** ✅:
1. ✅ Define IPC API in `src/preload.ts` (contextBridge) - 100% coverage
2. ✅ Implement IPC handlers in `src/main.ts` - All handlers registered
3. ✅ Create agent service wrapper in main process (`src/services/agent-service.ts`) - 100% coverage
4. ✅ Forward SSE events from main to renderer (`src/services/sse-bridge.ts`) - 98.09% coverage

**Refactor** ✅:
1. ✅ Extract common types to shared module (`src/preload-api.ts`)
2. ✅ Add retry logic with exponential backoff (2^(n-1) * 1000ms, max 30s)
3. ✅ Extract shared API client utilities (`src/shared/api-client.ts`) - DRY principle applied

**Final Test Coverage**:
- **92 tests passing** across 12 test suites
- **99.44% statement coverage**, 95.94% branch coverage, 100% function coverage
- All core modules: 100% coverage (preload, agent-service, task-service, api-client)
- SSE bridge: 98.09% statement, 86.95% branch

**Key Achievements**:
- Implemented secure IPC bridge with contextBridge
- Created type-safe APIs for agent/task operations
- Built SSE streaming with automatic reconnection
- Applied DRY principle: extracted shared utilities to eliminate 150+ lines of duplication
- Achieved comprehensive test coverage following TDD methodology

**Detailed Documentation**: See [/.omx/plans/phase-1-1-ipc-bridge-foundation-tdd.md](../../.omx/plans/phase-1-1-ipc-bridge-foundation-tdd.md)

### Phase 1.2: Task Management (RED → GREEN → REFACTOR) ✅ COMPLETED

**Status**: ✅ Completed on 2026-06-25

**Tests (RED)** ✅:
1. ✅ Task status polling tests (19 tests in `task-adapter.test.ts`)
2. ✅ Task cancellation tests
3. ✅ Workspace data fetching tests
4. ✅ Multi-task concurrent execution tests
5. ✅ Error handling and retry logic tests

**Implementation (GREEN)** ✅:
1. ✅ Task adapter with IPC integration (`src/renderer/adapters/task-adapter.ts`)
2. ✅ Task queue with priority management (`src/renderer/adapters/task-queue.ts`)
3. ✅ Task status polling with exponential backoff
4. ✅ Task result caching to reduce IPC overhead

**Refactor** ✅:
1. ✅ Optimized polling intervals with exponential backoff (2s → 3s → 4.5s → 10s max)
2. ✅ Added task queue management (priority-based, max 5 concurrent, retry with backoff)
3. ✅ Implemented task result caching (5s TTL, invalidation on updates)

**Final Test Coverage**:
- **19/19 tests passing** in task-adapter test suite
- **task-adapter.ts**: 90.97% statement coverage, 91.42% branch coverage, 90.47% function coverage
- **task-queue.ts**: 80.7% statement coverage, 88.88% branch coverage, 80% function coverage

**Key Features Implemented**:
- Exponential backoff for long-running task polling (reduces server load)
- Priority-based task queue (HIGH > NORMAL > LOW)
- Automatic retry with exponential backoff (3 attempts, 1s → 2s → 4s delays)
- Task result caching with TTL and invalidation
- Terminal status detection (COMPLETED, FAILED, CANCELLED)
- Event-based status updates via IPC
- Multi-task concurrent polling support

**Detailed Documentation**: See implementation in `src/renderer/adapters/task-adapter.ts` and `src/renderer/adapters/task-queue.ts`

## Key Technical Decisions

1. **SSE in Electron**: Use main process to establish SSE connections, forward events via IPC
2. **Authentication**: Store tokens in main process, use `safeStorage` API for encryption
3. **State Management**: Keep renderer-side zustand store, sync via IPC events
4. **API Base URL**: Configure via environment variable, default to `http://localhost:8000`
5. **Error Recovery**: Implement exponential backoff for IPC retries, surface errors in UI

## Files to Create/Modify

### New Files:
- `apps/desktop-app/src/services/agent-service.ts` - Main process agent operations
- `apps/desktop-app/src/services/sse-bridge.ts` - SSE to IPC bridge
- `apps/desktop-app/src/preload-api.ts` - Type-safe IPC API definitions
- `apps/desktop-app/src/__tests__/agent-ipc.test.ts` - Agent IPC tests
- `apps/desktop-app/src/__tests__/task-ipc.test.ts` - Task IPC tests
- `apps/desktop-app/src/__tests__/sse-bridge.test.ts` - SSE bridge tests

### Modified Files:
- `apps/desktop-app/src/main.ts` - Register IPC handlers
- `apps/desktop-app/src/preload.ts` - Expose IPC API via contextBridge
- `apps/desktop-app/vite.config.ts` - Add preload script build
