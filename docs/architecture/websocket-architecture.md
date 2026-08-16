# WebSocket Architecture

> Status: implemented. The checklist below is retained as verified acceptance evidence; active gaps are tracked only in `docs/TASKS.md`.

**Status:** Phase 2-Lite Implementation
**Last Updated:** 2026-06-30

---

## Overview

This document describes the real-time infrastructure extracted from observability/teams polling patterns into a shared, reusable library.

## Architecture

### Core Components

1. **`lib/realtime/client.ts`** - Low-level SSE client with reconnection logic
2. **`lib/realtime/subscription.ts`** - React hook wrapper for lifecycle management
3. **`types/teamActivity.ts`** - TeamActivity event schema

### Design Principles

- **Transport-agnostic abstraction** - Currently SSE, can swap to WebSocket without consumer changes
- **Automatic reconnection** - Exponential backoff with configurable max delay
- **React-friendly** - Hooks-based API with proper cleanup
- **Type-safe** - Generic type parameter for event payloads

---

## Usage

### Basic Subscription

```typescript
import { useRealtimeSubscription } from '@/lib/realtime/subscription'
import { TeamActivity, isTeamActivity } from '@/types/teamActivity'

function MyComponent({ teamId }: { teamId: string }) {
  const subscription = useRealtimeSubscription<TeamActivity>(
    (lastEventId) => `/api/teams/${teamId}/activity/stream?lastEventId=${lastEventId}`,
    {
      parse: (data) => JSON.parse(data),
      onMessage: (activity) => {
        if (isTeamActivity(activity)) {
          console.log('Activity received:', activity)
        }
      },
      onStatus: (status) => {
        if (status === 'failed') {
          showNotification('Connection lost, retrying...')
        }
      },
    }
  )

  return (
    <div>
      Status: {subscription.status}
      {subscription.connected && <span>✓ Connected</span>}
    </div>
  )
}
```

### Custom Event Types

```typescript
interface CustomEvent {
  type: 'notification' | 'alert'
  message: string
  timestamp: string
}

const subscription = useRealtimeSubscription<CustomEvent>(
  (lastEventId) => `/api/events/stream?lastEventId=${lastEventId}`,
  {
    parse: (data) => JSON.parse(data),
    onMessage: (event) => {
      // Handle custom event
    },
  }
)
```

---

## Interface Contract for Phase 2-Full

### Required Exports

Phase 2-Full (Teams UI) depends on:

1. **`useRealtimeSubscription<T>`** - Primary subscription hook
2. **`TeamActivity` type** - Event schema
3. **`isTeamActivity` type guard** - Runtime validation
4. **`SubscriptionHandle` type** - Return type of subscription hook

### Backend Contract

Server-sent events must follow this format:

```
event: message
id: <sequence-number>
data: {"id":"abc","userId":"u1","userName":"Alice","action":"terminal_created",...}

event: message
id: <sequence-number>
data: {"id":"def","userId":"u2","userName":"Bob","action":"comment_added",...}
```

**Required fields:**
- `id` - Event ID (for reconnection resume via `lastEventId`)
- `data` - JSON-encoded TeamActivity object

---

## Reconnection Behavior

### Exponential Backoff

```
Attempt 1: 1s delay
Attempt 2: 2s delay
Attempt 3: 4s delay
Attempt 4: 8s delay
Attempt 5+: 30s delay (max)
```

### User Notifications

- **Before 5 attempts**: Silent retries (status = "retrying")
- **After 5 attempts**: Show warning toast (status = "failed")
- **On reconnect**: Clear warning, status = "open"

### Resume from Last Event

The `urlFactory` receives `lastEventId` from previous connection:

```typescript
(lastEventId) => {
  const url = '/api/stream'
  return lastEventId ? `${url}?lastEventId=${lastEventId}` : url
}
```

Server should:
1. Parse `lastEventId` query param
2. Send all events **after** that ID
3. Continue streaming new events

---

## Migration from Existing Code

### Before (teams/observability)

```typescript
// Scattered polling logic
useEffect(() => {
  const interval = setInterval(() => {
    fetch('/api/team/activity').then(...)
  }, 5000)
  return () => clearInterval(interval)
}, [])
```

### After (shared realtime)

```typescript
import { useRealtimeSubscription } from '@/lib/realtime/subscription'

useRealtimeSubscription<TeamActivity>(
  (lastEventId) => `/api/team/activity/stream?lastEventId=${lastEventId}`,
  {
    parse: (data) => JSON.parse(data),
    onMessage: (activity) => {
      // Push-based, no polling
    },
  }
)
```

---

## Testing Strategy

### Unit Tests

- `client.ts` - Connection, reconnection, error handling
- `subscription.ts` - React lifecycle, cleanup on unmount
- `teamActivity.ts` - Type guards, schema validation

### Integration Tests

- Mock EventSource with reconnection scenarios
- Verify `lastEventId` resume logic
- Test status transitions (connecting → open → retrying → failed)

### E2E Tests

Phase 2-Full will add:
- Real backend SSE endpoint
- Multi-user activity stream synchronization
- Network interruption simulation

---

## Phase 2-Full Dependencies

This infrastructure enables Phase 2-Full to:

1. **Build activity feed UI** - Consume TeamActivity stream
2. **Show real-time presence** - "Alice created terminal 3 seconds ago"
3. **Handle reconnection gracefully** - No data loss on resume
4. **Delete observability polling** - Shared abstraction replaces ad-hoc code

---

## Observability Compatibility

**Critical:** This extraction does NOT break existing observability features.

- Observability can continue using `useSSE` hook (unchanged)
- New code should migrate to `useRealtimeSubscription` (identical API)
- Phase 3 pruning will remove observability entirely (no migration needed)

---

## Future Enhancements (Out of Scope)

- WebSocket fallback (SSE sufficient for Phase 2-Full)
- Message queue persistence (server-side concern)
- Client-side message deduplication (handled by sequence IDs)
- Binary protocol (JSON sufficient for activity streams)

---

## Acceptance Criteria (Phase 2-Lite)

- [x] `lib/realtime/client.ts` created with reconnection logic
- [x] `lib/realtime/subscription.ts` created with React hook
- [x] `types/teamActivity.ts` created with schema definition
- [x] This documentation file created
- [x] Unit tests pass (client, subscription, type guards)
- [x] Integration test: Mock EventSource reconnection
- [x] Observability features still functional (no regression)
- [x] Phase 1 team confirms contract sufficient for multi-terminal sharing

---

**Next Phase:** Phase 1 (Multi-Terminal Architecture) can now reference this WebSocket abstraction for terminal sharing features.
