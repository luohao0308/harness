import { useCallback, type ChangeEvent, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { feedbackErrorMessage, notifyFeedback } from "../../../../components/ui/feedback-toast";
import type { ComposerAttachment } from "../../../agents/components/ChatComposer";
import type { WorkspaceMode } from "../../../agents/lib/types";
import { sendTeamMessage, type Team, type TeamAgent, type TeamMailboxMessage } from "../../../tasks/api";

import {
  agentMessages,
  attachmentKey,
  fileToComposerAttachment,
  findLastAssistantEntry,
  previousUserEntry,
  recipientSlotIdsForTarget,
  teamConversationEntriesWithPending,
  teamPendingSendKey,
} from "./conversation";
import type {
  ComposerState,
  PendingSend,
  SettledWakeCutoffs,
  StreamingWake,
  TeamBottomPanel,
  TeamBranchGroupsBySlot,
  TeamComposerStateUpdater,
  TeamConversationEntry,
  TextFn,
} from "./types";

type UseTeamComposerActionsArgs = {
  teamId: string;
  activeTeam: Team | null;
  agents: TeamAgent[];
  messages: TeamMailboxMessage[];
  pendingSends: PendingSend[];
  pendingWakeSlotIds: string[];
  streamingWakes: StreamingWake[];
  settledWakeCutoffs: SettledWakeCutoffs;
  pendingSendKeysRef: MutableRefObject<Set<string>>;
  teamFileInputsRef: MutableRefObject<Record<string, HTMLInputElement | null>>;
  setComposerState: Dispatch<SetStateAction<ComposerState>>;
  setPendingSends: Dispatch<SetStateAction<PendingSend[]>>;
  setStreamingWakes: Dispatch<SetStateAction<StreamingWake[]>>;
  setAttachmentsBySlotId: Dispatch<SetStateAction<Record<string, ComposerAttachment[]>>>;
  setBottomPanelBySlotId: Dispatch<SetStateAction<Record<string, TeamBottomPanel>>>;
  setBranchGroupsBySlotId: Dispatch<SetStateAction<TeamBranchGroupsBySlot>>;
  triggerWake: (slotIds: string[]) => void;
  invalidateTeam: () => Promise<void>;
  text: TextFn;
};

type TeamSendMutation = UseMutationResult<unknown, Error, PendingSend, unknown>;

type BranchSendOptions = {
  anchorUserId: string;
  originalAssistantId: string;
};

export function useTeamComposerActions({
  teamId,
  activeTeam,
  agents,
  messages,
  pendingSends,
  pendingWakeSlotIds,
  streamingWakes,
  settledWakeCutoffs,
  pendingSendKeysRef,
  teamFileInputsRef,
  setComposerState,
  setPendingSends,
  setStreamingWakes,
  setAttachmentsBySlotId,
  setBottomPanelBySlotId,
  setBranchGroupsBySlotId,
  triggerWake,
  invalidateTeam,
  text,
}: UseTeamComposerActionsArgs) {
  const sendMutation: TeamSendMutation = useMutation({
    mutationFn: (payload: PendingSend) =>
      sendTeamMessage(teamId, {
        target: payload.target,
        content: payload.content,
        from_agent_slot_id: "user",
        type: "message",
        files: payload.files,
        mode: payload.mode,
      }),
    onSuccess: async (_message, variables) => {
      triggerWake(variables.recipientSlotIds);
      await invalidateTeam();
    },
    onError: (error, variables) => {
      if (variables.branchAssistantId) {
        setStreamingWakes((current) =>
          current.filter((wake) => wake.branchAssistantId !== variables.branchAssistantId),
        );
      }
      notifyFeedback({
        tone: "error",
        title: text("团队消息发送失败", "Team message send failed"),
        description: feedbackErrorMessage(
          error,
          text("请检查当前团队状态、目标成员或稍后重试。", "Check the team state, recipient, or retry."),
        ),
      });
    },
    onSettled: (_message, _error, variables) => {
      if (!variables) return;
      pendingSendKeysRef.current.delete(variables.key);
      setPendingSends((current) => current.filter((send) => send.id !== variables.id));
    },
  });

  const updateComposer = useCallback((slotId: string, next: TeamComposerStateUpdater) => {
    setComposerState((current) => {
      const previous = current[slotId] ?? { draft: "" };
      const resolved = typeof next === "function" ? next(previous) : next;
      return { ...current, [slotId]: resolved };
    });
  }, [setComposerState]);

  const sendFromComposer = useCallback(
    (
      agent: TeamAgent,
      content: string,
      target: string,
      attachments: ComposerAttachment[] = [],
      mode: WorkspaceMode = "chat",
      branchOptions?: BranchSendOptions,
    ) => {
      const trimmed = content.trim();
      if (!trimmed || !activeTeam) return;
      const recipientSlotIds = recipientSlotIdsForTarget(activeTeam, target);
      if (recipientSlotIds.length === 0) return;
      const files = attachments.map((attachment) => attachment.name);
      const key = teamPendingSendKey(agent.slot_id, target, mode, trimmed, files);
      const duplicate =
        pendingSendKeysRef.current.has(key) ||
        pendingSends.some(
          (send) =>
            send.sourceSlotId === agent.slot_id &&
            send.target === target &&
            send.content === trimmed &&
            send.mode === mode &&
            send.files.join("\n") === files.join("\n"),
        );
      if (duplicate) return;
      pendingSendKeysRef.current.add(key);
      const pendingSendId = `${key}:${Date.now()}`;
      const branchAssistantId = branchOptions
        ? `team-${teamId}-${agent.slot_id}-branch-${encodeURIComponent(pendingSendId)}`
        : undefined;
      const pendingSend: PendingSend = {
        id: pendingSendId,
        key,
        sourceSlotId: agent.slot_id,
        target,
        content: trimmed,
        files,
        mode,
        recipientSlotIds,
        anchorUserId: branchOptions?.anchorUserId,
        branchAssistantId,
      };
      setPendingSends((current) => [...current, pendingSend]);
      if (branchOptions && branchAssistantId) {
        setStreamingWakes((current) =>
          current.some((wake) => wake.branchAssistantId === branchAssistantId)
            ? current
            : [
                ...current,
                {
                  slotId: agent.slot_id,
                  content: "",
                  anchorUserId: branchOptions.anchorUserId,
                  branchAssistantId,
                },
              ],
        );
        setBranchGroupsBySlotId((current) => {
          const slotGroups = current[agent.slot_id] ?? {};
          const existing = slotGroups[branchOptions.anchorUserId];
          const branchNodeIds = Array.from(
            new Set([
              ...(existing?.branchNodeIds ?? []),
              branchOptions.originalAssistantId,
              branchAssistantId,
            ]),
          );
          return {
            ...current,
            [agent.slot_id]: {
              ...slotGroups,
              [branchOptions.anchorUserId]: {
                anchorUserId: branchOptions.anchorUserId,
                anchorContent: trimmed,
                branchNodeIds,
                hiddenUserNodeIds: existing?.hiddenUserNodeIds ?? [],
                activeNodeId: branchAssistantId,
              },
            },
          };
        });
      }
      setComposerState((current) => ({
        ...current,
        [agent.slot_id]: { ...(current[agent.slot_id] ?? {}), draft: "", mode },
      }));
      setAttachmentsBySlotId((current) => ({ ...current, [agent.slot_id]: [] }));
      sendMutation.mutate(pendingSend);
    },
    [
      activeTeam,
      pendingSendKeysRef,
      pendingSends,
      sendMutation,
      setAttachmentsBySlotId,
      setBranchGroupsBySlotId,
      setComposerState,
      setPendingSends,
      setStreamingWakes,
      teamId,
    ],
  );

  const sendFromMessageAction = useCallback(
    (sourceSlotId: string, content: string, target: string) => {
      const trimmed = content.trim();
      const sourceAgent = agents.find((agent) => agent.slot_id === sourceSlotId);
      if (!trimmed || !sourceAgent) return;
      sendFromComposer(sourceAgent, trimmed, target);
    },
    [agents, sendFromComposer],
  );

  const branchFromAssistant = useCallback(
    (agent: TeamAgent, entries: TeamConversationEntry[], assistantNodeId: string) => {
      const previousUser = previousUserEntry(entries, assistantNodeId);
      if (!previousUser) return;
      const originalAssistant = entries.find((entry) => entry.node.id === assistantNodeId);
      if (!originalAssistant) return;
      sendFromComposer(agent, previousUser.node.content, previousUser.target, [], "chat", {
        anchorUserId: previousUser.node.id,
        originalAssistantId: originalAssistant.node.id,
      });
    },
    [sendFromComposer],
  );

  const switchTeamBranch = useCallback((slotId: string, anchorUserId: string, nodeId: string) => {
    setBranchGroupsBySlotId((current) => {
      const slotGroups = current[slotId];
      const group = slotGroups?.[anchorUserId];
      if (!slotGroups || !group || !group.branchNodeIds.includes(nodeId)) return current;
      return {
        ...current,
        [slotId]: {
          ...slotGroups,
          [anchorUserId]: { ...group, activeNodeId: nodeId },
        },
      };
    });
  }, [setBranchGroupsBySlotId]);

  const syncBranchGroups = useCallback((team: Team | null) => {
    if (!team) return;
    setBranchGroupsBySlotId((current) => {
      let changed = false;
      const next: TeamBranchGroupsBySlot = { ...current };
      for (const agent of team.agents) {
        const slotGroups = current[agent.slot_id];
        if (!slotGroups) continue;
        const entries = teamConversationEntriesWithPending(
          team,
          agent,
          agentMessages(agent, messages),
          pendingSends,
          pendingWakeSlotIds,
          streamingWakes,
          settledWakeCutoffs,
        );
        const byId = new Map(entries.map((entry) => [entry.node.id, entry]));
        let nextSlotGroups = slotGroups;
        for (const [anchorUserId, group] of Object.entries(slotGroups)) {
          const visibleBranchNodeIds = group.branchNodeIds.filter((nodeId) => byId.has(nodeId));
          const activeBranchWasReplaced = !visibleBranchNodeIds.includes(group.activeNodeId);
          let workingGroup = group;
          if (
            visibleBranchNodeIds.length !== group.branchNodeIds.length ||
            activeBranchWasReplaced
          ) {
            workingGroup = {
              ...group,
              branchNodeIds: visibleBranchNodeIds,
              activeNodeId: visibleBranchNodeIds.includes(group.activeNodeId)
                ? group.activeNodeId
                : visibleBranchNodeIds[visibleBranchNodeIds.length - 1] ?? group.activeNodeId,
            };
            nextSlotGroups = {
              ...nextSlotGroups,
              [anchorUserId]: workingGroup,
            };
            changed = true;
          }
          const lastAssistant = findLastAssistantEntry(entries);
          const pendingBranch =
            lastAssistant &&
            lastAssistant.node.state !== "streaming" &&
            !workingGroup.branchNodeIds.includes(lastAssistant.node.id) &&
            previousUserEntry(entries, lastAssistant.node.id)?.node.content === workingGroup.anchorContent;
          if (!pendingBranch) continue;
          const nextBranchNodeIds = [...workingGroup.branchNodeIds, lastAssistant.node.id];
          const hiddenUserNodeIds = new Set(workingGroup.hiddenUserNodeIds);
          const previousUser = previousUserEntry(entries, lastAssistant.node.id);
          if (previousUser && previousUser.node.id !== workingGroup.anchorUserId) {
            hiddenUserNodeIds.add(previousUser.node.id);
          }
          nextSlotGroups = {
            ...nextSlotGroups,
            [anchorUserId]: {
              ...workingGroup,
              branchNodeIds: nextBranchNodeIds,
              hiddenUserNodeIds: [...hiddenUserNodeIds].filter((nodeId) => byId.has(nodeId)),
              activeNodeId: activeBranchWasReplaced
                ? lastAssistant.node.id
                : workingGroup.activeNodeId,
            },
          };
          changed = true;
        }
        if (nextSlotGroups !== slotGroups) next[agent.slot_id] = nextSlotGroups;
      }
      return changed ? next : current;
    });
  }, [
    messages,
    pendingSends,
    pendingWakeSlotIds,
    settledWakeCutoffs,
    setBranchGroupsBySlotId,
    streamingWakes,
  ]);

  const addComposerFiles = useCallback((slotId: string) => {
    teamFileInputsRef.current[slotId]?.click();
  }, [teamFileInputsRef]);

  const handleComposerFilesSelected = useCallback((slotId: string, event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.currentTarget.files ?? []);
    if (files.length === 0) return;
    setAttachmentsBySlotId((current) => {
      const existing = current[slotId] ?? [];
      const existingKeys = new Set(existing.map(attachmentKey));
      const next = [...existing];
      for (const file of files) {
        if (next.length >= 12) break;
        const attachment = fileToComposerAttachment(file);
        const key = attachmentKey(attachment);
        if (existingKeys.has(key)) continue;
        next.push(attachment);
        existingKeys.add(key);
      }
      return { ...current, [slotId]: next };
    });
    event.currentTarget.value = "";
  }, [setAttachmentsBySlotId]);

  const removeComposerAttachment = useCallback((slotId: string, attachmentId: string) => {
    setAttachmentsBySlotId((current) => ({
      ...current,
      [slotId]: (current[slotId] ?? []).filter((attachment) => attachment.id !== attachmentId),
    }));
  }, [setAttachmentsBySlotId]);

  const setComposerBottomPanel = useCallback((slotId: string, panel: TeamBottomPanel) => {
    setBottomPanelBySlotId((current) => ({ ...current, [slotId]: panel }));
  }, [setBottomPanelBySlotId]);

  return {
    addComposerFiles,
    branchFromAssistant,
    handleComposerFilesSelected,
    removeComposerAttachment,
    sendFromComposer,
    sendFromMessageAction,
    setComposerBottomPanel,
    switchTeamBranch,
    syncBranchGroups,
    updateComposer,
  };
}
