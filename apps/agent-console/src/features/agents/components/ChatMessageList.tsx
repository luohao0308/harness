/**
 * ChatMessageList — scrollable middle region of the ChatSurface layout.
 *
 * v4 rewrite (Req 2, Properties P20–P22):
 *   - Auto-follow is now driven by the pure `reduceAutoFollow` state
 *     machine in `lib/autoScrollFollow.ts`. We keep React state synchronous
 *     by calling the reducer inline and using its return value in the same
 *     layout effect so snapping happens the same frame the event fires.
 *   - `forwardRef` exposes an imperative `notifyUserSubmit()` handle so the
 *     parent (`ChatSurface.handleSubmit`) can inject the `user_submit`
 *     event without lifting follow state out of this component (Req 2.2).
 *   - The zero-height sentinel remains the `IntersectionObserver` target;
 *     the callback translates entries into `user_scroll_up` /
 *     `user_scroll_to_bottom` events (Req 2.9).
 *   - When the runtime lacks `IntersectionObserver` (JSDOM) we degrade to
 *     `{ autoFollow: true, showJumpButton: false }` so the layout effect
 *     still pins to the bottom on every content change (Req 2.10).
 *
 * v4 rendering (Req 7.3, Property P24):
 *   - Active path → `groupByRole(path)` → `<section role="group">` wrappers.
 *     Only the first node in each group renders the role avatar strip; the
 *     rest share a thinner divider so consecutive assistant deltas merge
 *     visually without breaking per-node Copy / Edit / Regenerate actions.
 *   - `tail` binding stays `activePath[activePath.length - 1]` so Property
 *     P8 (MetadataStrip ↔ last node) is unaffected.
 *
 * v2 contract retained (Req 1.1, 1.2, 1.3, 8.4 / Property P1):
 *   - Outer scroller is full-width; reading column uses `max-w-[80ch]
 *     lg:max-w-[56rem]` + responsive padding.
 *   - Plumbs edit / copy / regenerate handlers to every `ChatMessageBubble`.
 */

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type JSX,
} from "react";

import type { ConversationNode } from "../../../stores/workspaceStore";
import {
  AUTO_FOLLOW_BREAK_THRESHOLD_PX,
  SNAP_TOLERANCE_PX,
  contentSum,
  reduceAutoFollow,
  type AutoFollowEvent,
  type AutoFollowState,
} from "../lib/autoScrollFollow";
import { groupByRole } from "../lib/groupByRole";
import type { InspectorSection } from "../lib/types";
import { ChatErrorBubble } from "./ChatErrorBubble";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { ChatRunSummary } from "./ChatRunSummary";
import { ChatWelcomeState } from "./ChatWelcomeState";
import { JumpToLatestButton } from "./JumpToLatestButton";

export type ChatMessageListProps = {
  /** Ordered conversation nodes from workspace root to `activeLeafId`. */
  activePath: ConversationNode[];

  // Fallback / empty-state info
  agentName: string;
  modelLabel: string;

  // Callbacks to parent (ChatSurface)
  onPickExamplePrompt: (prompt: string) => void;
  onRetry: (nodeId: string) => void;
  onOpenInspector: (section: InspectorSection, nodeId: string) => void;

  // Run summary info
  activeRunId: string | null;
  runStatus?: string;
  runCreatedAt?: string;

  // v2 additions (Req 4 / Req 5 / Req 10)
  editingNodeId: string | null;
  onStartEdit: (nodeId: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: (nodeId: string, newContent: string) => void;
  onCopy: (nodeId: string) => Promise<boolean>;
  onRegenerate: (nodeId: string) => void;
  isStreaming: boolean;
};

export type ChatMessageListHandle = {
  /** Force `Auto_Follow = true` and snap to bottom (Req 2.2). */
  notifyUserSubmit: () => void;
};

export const ChatMessageList = forwardRef<
  ChatMessageListHandle,
  ChatMessageListProps
>(function ChatMessageList(props, forwardedRef): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sentinelRef = useRef<HTMLDivElement | null>(null);
  const [followState, setFollowState] = useState<AutoFollowState>({
    autoFollow: true,
    showJumpButton: false,
  });
  const followStateRef = useRef<AutoFollowState>(followState);
  followStateRef.current = followState;

  const previousContentSum = useRef<number>(0);
  const currentContentSum = contentSum(props.activePath);

  const snapToBottom = (): void => {
    const container = containerRef.current;
    if (container === null) return;
    container.scrollTop = container.scrollHeight - container.clientHeight;
  };

  const dispatchEvent = (
    event: AutoFollowEvent,
    options: { scrollBehavior?: ScrollBehavior } = {},
  ): AutoFollowState => {
    const decision = reduceAutoFollow(followStateRef.current, event);
    const next: AutoFollowState = {
      autoFollow: decision.autoFollow,
      showJumpButton: decision.showJumpButton,
    };
    followStateRef.current = next;
    setFollowState(next);
    if (decision.shouldSnapToBottom) {
      if (options.scrollBehavior === "smooth") {
        const container = containerRef.current;
        if (container !== null) {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: "smooth",
          });
        }
      } else {
        snapToBottom();
      }
    }
    return next;
  };

  useImperativeHandle(
    forwardedRef,
    () => ({
      notifyUserSubmit: (): void => {
        dispatchEvent({ type: "user_submit" });
      },
    }),
    // dispatchEvent closure stable — reading refs at call time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // ── IntersectionObserver bridge (Req 2.9 / 2.10) ─────────────────────
  useEffect(() => {
    const container = containerRef.current;
    const sentinel = sentinelRef.current;
    if (container === null || sentinel === null) return;
    if (typeof IntersectionObserver === "undefined") {
      // JSDOM fallback — layout effect still pins to bottom.
      setFollowState({ autoFollow: true, showJumpButton: false });
      followStateRef.current = { autoFollow: true, showJumpButton: false };
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const distance = Math.max(
            0,
            container.scrollHeight - container.scrollTop - container.clientHeight,
          );
          if (
            entry.isIntersecting ||
            distance <= SNAP_TOLERANCE_PX
          ) {
            dispatchEvent({
              type: "user_scroll_to_bottom",
              distanceToBottomPx: distance,
            });
          } else {
            dispatchEvent({
              type: "user_scroll_up",
              distanceToBottomPx: distance,
            });
          }
        }
      },
      { root: container, threshold: 0, rootMargin: "0px" },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
    // dispatchEvent reads refs; effect must run once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Track manual scrolls inside the 200 px buffer (Req 2.5 / 2.6) ────
  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return;
    const onScroll = (): void => {
      const distance = Math.max(
        0,
        container.scrollHeight - container.scrollTop - container.clientHeight,
      );
      if (distance <= SNAP_TOLERANCE_PX) {
        dispatchEvent({
          type: "user_scroll_to_bottom",
          distanceToBottomPx: distance,
        });
      } else if (distance > AUTO_FOLLOW_BREAK_THRESHOLD_PX) {
        dispatchEvent({
          type: "user_scroll_up",
          distanceToBottomPx: distance,
        });
      } else {
        dispatchEvent({
          type: "user_scroll_up",
          distanceToBottomPx: distance,
        });
      }
    };
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Assistant delta detection (Req 2.3 / 2.4) ────────────────────────
  useLayoutEffect(() => {
    const prev = previousContentSum.current;
    previousContentSum.current = currentContentSum;
    if (currentContentSum > prev) {
      dispatchEvent({ type: "assistant_delta" });
    } else if (followStateRef.current.autoFollow) {
      // Path switch / non-delta update while following → still snap.
      snapToBottom();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentContentSum, props.activePath.length]);

  const handleJump = (): void => {
    dispatchEvent({ type: "jump_to_latest_click" }, { scrollBehavior: "smooth" });
  };

  // All hooks MUST run on every render before any conditional early-return
  // (React error #310). The welcome-state branch below does not use
  // `groups` but we still compute it here to keep the hook order stable.
  const groups = useMemo(
    () => groupByRole(props.activePath),
    [props.activePath],
  );

  if (props.activePath.length === 0) {
    return (
      <div className="relative flex-1 min-h-0 w-full">
        <div
          ref={containerRef}
          className="absolute inset-0 overflow-y-auto"
        >
          <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col justify-center gap-5 px-4 py-8 sm:px-6">
            <ChatWelcomeState
              agentName={props.agentName}
              modelLabel={props.modelLabel}
              onPickPrompt={props.onPickExamplePrompt}
            />
          </div>
          <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
        </div>
      </div>
    );
  }

  const lastAssistant = findLastAssistant(props.activePath);
  const lastAssistantId = lastAssistant?.id ?? null;
  const showRunSummary =
    props.activeRunId != null &&
    props.activeRunId.length > 0 &&
    lastAssistant !== null &&
    lastAssistant.state === "done" &&
    typeof lastAssistant.run_id === "string" &&
    lastAssistant.run_id.length > 0;

  return (
    <div className="relative flex-1 min-h-0 w-full">
      <div
        ref={containerRef}
        className="absolute inset-0 overflow-y-auto"
      >
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
          {groups.map((group, groupIdx) => (
            <section
              key={`group-${groupIdx}`}
              role="group"
              aria-label={`${group.role}-messages`}
              className="flex flex-col gap-3"
            >
              {group.nodes.map((node) => {
                if (node.state === "error" && node.metadata.error) {
                  return (
                    <ChatErrorBubble
                      key={node.id}
                      node={node}
                      error={node.metadata.error}
                      onRetry={() => props.onRetry(node.id)}
                    />
                  );
                }
                const canRegenerate =
                  node.role === "assistant" &&
                  node.id === lastAssistantId &&
                  (node.state === "done" ||
                    node.state === "error" ||
                    node.state === "paused");
                return (
                  <ChatMessageBubble
                    key={node.id}
                    node={node}
                    onOpenInspector={props.onOpenInspector}
                    editingNodeId={props.editingNodeId}
                    onStartEdit={props.onStartEdit}
                    onCancelEdit={props.onCancelEdit}
                    onSaveEdit={props.onSaveEdit}
                    canRegenerate={canRegenerate}
                    isStreaming={props.isStreaming}
                    onCopy={props.onCopy}
                    onRegenerate={props.onRegenerate}
                  />
                );
              })}
            </section>
          ))}
          {showRunSummary && props.activeRunId && (
            <ChatRunSummary
              runId={props.activeRunId}
              runStatus={props.runStatus}
              runCreatedAt={props.runCreatedAt}
            />
          )}
        </div>
        <div ref={sentinelRef} aria-hidden="true" style={{ height: 1 }} />
      </div>
      {followState.showJumpButton && !followState.autoFollow && (
        <JumpToLatestButton onClick={handleJump} />
      )}
    </div>
  );
});

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

function findLastAssistant(nodes: ConversationNode[]): ConversationNode | null {
  for (let i = nodes.length - 1; i >= 0; i -= 1) {
    const candidate = nodes[i];
    if (candidate.role === "assistant") return candidate;
  }
  return null;
}
