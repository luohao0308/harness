# Team Mode Product Surface Target

## Target Reset

Harness Team Mode is not a Run, Trace, Observability, assignment, or Agent Workspace
variant. Runs and sessions may exist as implementation evidence, but they must not shape the
Team Mode product surface. The user-facing result is a long-lived team collaboration room
with a Leader, teammates, mailboxes, wake/status transitions, task steps, and horizontal chat
columns.

Use Harness colors, typography scale, and slate/page/panel tokens only as the skin. Structure,
message routing, wake behavior, and backend-visible semantics must follow the Harness Team
Mode contract below.

## Product Invariant

There is exactly one Team Session product model:

1. The user creates or opens a Team.
2. The Team owns one Leader slot and zero or more teammate slots.
3. Each slot owns an independent conversation column and mailbox.
4. User messages are delivered by mailbox, then the target slot is woken.
5. Agents coordinate exclusively through `team_*` tools that write mail, mutate tasks, spawn,
   rename, or request shutdown.
6. Status and event projection update the Team UI without turning it into a Run Detail screen.

## Communication Contract

Team communication behavior:

- User message from the Leader column goes to the Leader mailbox.
- User message from a teammate column goes directly to that teammate mailbox.
- Mail is persisted before wake.
- Wake reads unread mail, atomically marks it read, builds the prompt, and changes status.
- First wake or failed recovery includes the full role prompt plus unread mail.
- Later wakes send only formatted unread mail.
- Teammate completion sets the teammate idle and writes `idle_notification` to Leader.
- Leader wakes on idle notifications only when all non-Leader teammates are settled.
- Duplicate active wake for a slot is ignored instead of starting a second turn.
- Teammate crash or inactivity preserves the slot, marks it failed, writes testament mail to
  Leader, and wakes Leader.
- Shutdown is a mail round trip: `shutdown_request` -> exact `shutdown_approved` removes the
  teammate; `shutdown_rejected: <reason>` keeps them and notifies Leader.

## Team Tool Contract

Harness must provide native team tools. Transport is FastAPI/SSE/SQLAlchemy and result text
must stay compact enough for agent-to-agent coordination:

- `team_send_message`: resolves slot id or agent name; `*` broadcasts to every non-sender slot.
- `team_spawn_agent`: Leader-only; creates slot, writes welcome mail, wakes new teammate.
- `team_task_create`: creates pending task with optional owner and dependency list.
- `team_task_update`: changes status/owner/description; completing a task unblocks dependents.
- `team_task_list`: returns a compact text board.
- `team_members`: returns name, backend/type, role, status, and model.
- `team_rename_agent`: Leader-only; preserves original-name hint.
- `team_shutdown_agent`: Leader-only; cannot target Leader; sends `shutdown_request`.

## UI Contract

The first viewport must preserve the Team Mode product shape:

- Harness ConsoleShell left navigation remains, but the Team product area uses Team Mode structure.
- Internal left rail lists teams and has a compact create entry.
- Main surface begins with compact agent tabs, not a dashboard.
- Tabs show Leader and teammates, status, unread/task/approval badges, rename, remove, and drag
  reorder behavior.
- Desktop columns are horizontal, start around 400px, share spare width for one/two agents, and
  scroll for many agents.
- Leader column has a subtle left emphasis; no new theme color is introduced.
- Each column owns its own header, message stream, `View Steps` foldout, and bottom composer.
- A column composer sends to that column's slot. It must not expose a generic dashboard-style
  target selector as the primary interaction.
- In the web default `多列` view, task details live in per-column `View Steps` or a transient
  compact popover/drawer. A persistent right-side task dashboard is not part of the web target
  first screen.
- Electron may add `协作` and `任务图` presentation modes beside the unchanged `多列` view.
  Their right-side inspector or task graph is a desktop workspace aid, not a Run/Trace dashboard,
  and must reuse the same Team session, mailbox, task, goal, and wake semantics.
- Mobile switches to one active column through tabs/dropdown and must not create document-level
  horizontal overflow at 390px.

## Backend Data Contract

Required entities:

- `Team`: long-lived session metadata, organization scope, workspace info, Leader slot.
- `TeamAgent`: slot id, agent definition/backend, name, role, model, status, session/runtime ids,
  wake metadata.
- `TeamMailboxMessage`: team, to/from slot, type, content, summary, read, file metadata, timestamp.
- `TeamTask`: subject, description, owner, status, blocked-by/blocks, metadata, timestamps.
- `TeamEvent`: append-only projection for create/rename/archive, agent changes, mail, read,
  wake/status, task changes, and tool-visible side effects.

## Explicit Non-Goals

- Do not implement Team Mode as a Run workspace mode.
- Do not make Run Detail, Trace, Observability, assignments, or handoffs the default Team screen.
- Do not keep a Harness control-panel task dashboard as the primary team experience.
- Do not claim completion from API green checks alone. Visual and communication semantics must be
  verified against the Team Mode contract and screenshots.

## Execution Order

1. Lock this target and test spec before further broad edits.
2. Align the column composer and tabs with the column-is-target interaction.
3. Align backend mailbox/wake/status/tool semantics with the Team Mode contracts above.
4. Remove or demote any Run/Trace/dashboard-centered Team UI.
5. Verify with backend tests, frontend tests, Playwright desktop/mobile smoke, and screenshots.

Desktop presentation details and visual acceptance are defined in
`docs/design/desktop/team-mode-workspace.md`.
