# Spec: Agent Workspace Context Compression

## Metadata

- Source: `$deep-interview`
- Profile: standard
- Final ambiguity: 0.10
- Threshold: 0.20
- Context type: brownfield
- Context snapshot: `.omx/context/context-compression-20260513T160102Z.md`
- Transcript: `.omx/interviews/context-compression-20260513T160102Z.md`

## Intent

Implement real context compression for Agent Workspace. The goal is to reduce future prompt tokens while preserving important conversation state, not merely change the token budget shown by the usage ring.

## Desired Outcome

When context usage reaches the configured compression threshold, the app should generate and manage a semantic summary of older conversation context. Future chat requests should use that summary plus recent/pinned messages instead of sending full raw history.

The UI should make compression visible and manageable from the header.

## In Scope

- Prompt-level summarization of older conversation history.
- Preserve full conversation history in the UI/store; do not permanently delete old messages.
- Use the generated summary for future chat requests.
- Keep current selective-dropping behavior as a fallback hard-budget mechanism.
- Add automatic compression:
  - Background pre-compression after assistant completion when usage reaches threshold.
  - Pre-send fallback compression before a new request if threshold is reached and no current summary is available/stale.
- Default context window: `258_000` tokens.
- Default auto-compression threshold: `80%`.
- Add settings for:
  - Context length.
  - Auto-compression ratio.
- Header changes:
  - Remove model display from the header.
  - Show managed compression summary UI in the header.
  - Header summary UI supports summary preview, recompress, clear summary, and covered message range.
- Composer changes:
  - Keep model selector/display near the send button.
  - Reduce composer width by roughly half compared with the current width.
- Manual compression:
  - Clicking the context usage control should trigger compression.

## Out Of Scope / Non-Goals

- No RAG/vector database for v1.
- No model-internal KV cache pruning, MQA/GQA, token merging, or gist-token implementation.
- No permanent deletion of old messages.
- Do not summarize or compress attachment contents in v1.
- Do not require a local model or new ML inference runtime for v1.

## Decision Boundaries

OMX may decide:
- Exact summary storage shape in Zustand/backend payload as long as old messages remain intact.
- Exact wording of summary prompt.
- Exact UI layout for the header management control.
- Whether compression runs through an existing chat stream endpoint or a new backend endpoint, as long as behavior is testable and clear.
- Exact stale-summary invalidation rule, provided it covers new messages after the compressed range.

OMX should not decide without confirmation:
- Adding a vector DB/RAG dependency.
- Adding a new external model provider requirement.
- Permanently mutating/deleting old conversation messages.
- Summarizing attachment body text.

## Technical Context Findings

- Current frontend request builder already trims payload with `truncateForContext`.
- Backend chat stream currently accepts `context_max_tokens`, but schema notes it is ignored by backend.
- Backend prompt construction uses recent `context_window_turns` plus pinned nodes.
- `RunContextRouter` has event trace compression but not chat conversation summary compression.
- External model APIs mean only app-layer prompt compression is viable for v1.

## Proposed Behavior

Compression summary state should track:
- Summary text.
- Source/covered node ids or first/last covered node ids.
- Created/updated timestamp.
- Estimated original tokens.
- Estimated summary tokens.
- Whether summary is stale.

Future request context should include:
- Compression summary as a system or assistant-context message.
- Pinned messages.
- Recent uncompressed conversation turns.
- Current user goal.

Compression should skip:
- Attachments.
- Already covered messages unless recompress is requested or summary is stale.
- In-flight assistant streaming.

## Acceptance Criteria

1. Header no longer shows the model label.
2. Header shows a context summary management control after compression exists.
3. The summary control shows preview/details and supports:
   - Recompress.
   - Clear summary.
   - View covered message range.
4. Bottom composer still shows the selected model near the send button.
5. Composer visual width is reduced by roughly 50%.
6. Default context budget is `258_000` tokens.
7. Default auto-compression threshold is `80%`.
8. Settings panel lets the user adjust context budget and auto-compression threshold.
9. Clicking the context usage control manually triggers compression.
10. After assistant completion, if estimated usage is at or above threshold, background compression runs.
11. Before sending, if estimated usage is at or above threshold and summary is missing or stale, compression runs before the chat request.
12. Future chat requests include the summary plus recent/pinned messages.
13. Old messages remain available; no permanent deletion occurs.
14. Attachment contents are not summarized/compressed.
15. Existing selective dropping remains as a fallback when final payload still exceeds budget.
16. Tests cover manual compression, automatic background compression, pre-send fallback compression, settings persistence, and payload construction.

## Risks

- Pre-send compression adds latency when the summary is missing/stale.
- Background compression may create extra model calls.
- Summary quality can drop important details unless prompt and coverage rules are tested.
- UI can become confusing if users cannot distinguish raw chat history from compressed request context.

## Recommended Implementation Lane

Use `$ralplan` next before implementation. This touches frontend state, backend API/model calls, request construction, and UI, so a short architecture/test plan is warranted.
