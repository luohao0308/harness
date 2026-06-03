import { useCallback, useRef, type Dispatch, type SetStateAction } from "react";

import { notifyFeedback } from "../../../../components/ui/feedback-toast";
import {
  COMPRESSION_PROMPT_VERSION,
  SUMMARY_SCHEMA_VERSION,
  normalizeModelId,
  serializeContextNode,
  type ContextCompressionSummary,
} from "../../../agents/lib/contextCompression";
import { compressAgentWorkspaceContext, type Team, type TeamAgent } from "../../../tasks/api";

import { teamCompressionKey, workspaceCompressionSummary } from "./conversation";
import type {
  TeamContextCompressions,
  TeamConversationEntry,
  TextFn,
} from "./types";

type ModelOption = {
  providerId: string;
  modelId: string;
};

type UseTeamContextCompressionArgs = {
  team: Team | null;
  contextCompressionsBySlotId: TeamContextCompressions;
  modelOptions: ModelOption[];
  pinnedMessageIds: string[];
  setContextCompressionsBySlotId: Dispatch<SetStateAction<TeamContextCompressions>>;
  text: TextFn;
};

export function useTeamContextCompression({
  team,
  contextCompressionsBySlotId,
  modelOptions,
  pinnedMessageIds,
  setContextCompressionsBySlotId,
  text,
}: UseTeamContextCompressionArgs) {
  const compressionInFlightRef = useRef<Set<string>>(new Set());

  const setTeamContextCompression = useCallback(
    (slotId: string, branchKey: string, summary: ContextCompressionSummary) => {
      setContextCompressionsBySlotId((current) => ({
        ...current,
        [slotId]: {
          ...(current[slotId] ?? {}),
          [branchKey]: summary,
        },
      }));
    },
    [setContextCompressionsBySlotId],
  );

  const clearTeamContextCompression = useCallback((slotId: string, branchKey: string) => {
    setContextCompressionsBySlotId((current) => {
      const slotSummaries = current[slotId];
      if (!slotSummaries || !(branchKey in slotSummaries)) return current;
      const { [branchKey]: _removed, ...nextSlotSummaries } = slotSummaries;
      if (Object.keys(nextSlotSummaries).length === 0) {
        const { [slotId]: _removedSlot, ...next } = current;
        return next;
      }
      return { ...current, [slotId]: nextSlotSummaries };
    });
  }, [setContextCompressionsBySlotId]);

  const compressTeamContext = useCallback(
    async (
      agent: TeamAgent,
      entries: TeamConversationEntry[],
      reason: "manual" | "background" | "pre_send" = "manual",
    ): Promise<ContextCompressionSummary | null> => {
      if (!team) return null;
      const branchKey = teamCompressionKey(team, agent, entries);
      if (compressionInFlightRef.current.has(branchKey)) {
        if (reason === "manual") {
          notifyFeedback({
            tone: "info",
            title: text("上下文仍在压缩", "Context compression is still running"),
            description: text(
              `“${agent.agent_name}”当前已经在生成摘要，请稍候再试。`,
              `${agent.agent_name} is already generating a summary. Please wait a moment.`,
            ),
          });
        }
        return null;
      }
      const activePath = entries.map((entry) => entry.node);
      const eligible = activePath.filter(
        (node) =>
          (node.role === "user" || node.role === "assistant" || node.role === "system") &&
          !pinnedMessageIds.includes(node.id) &&
          node.content.trim().length > 0,
      );
      if (eligible.length === 0) {
        if (reason === "manual") {
          notifyFeedback({
            tone: "warning",
            title: text("暂无可压缩内容", "Nothing to compress yet"),
            description: text(
              `“${agent.agent_name}”至少需要一段未固定的对话内容后，才能生成摘要。`,
              `${agent.agent_name} needs some unpinned conversation content before a summary can be generated.`,
            ),
          });
        }
        return null;
      }

      const slotSummaries = contextCompressionsBySlotId[agent.slot_id] ?? {};
      const selectedProviderId = agent.model_provider || modelOptions[0]?.providerId || null;
      const selectedModelId = agent.model_name || modelOptions[0]?.modelId || null;
      const existing = reason === "manual" ? null : slotSummaries[branchKey] ?? null;
      const now = new Date().toISOString();
      compressionInFlightRef.current.add(branchKey);
      setTeamContextCompression(agent.slot_id, branchKey, {
        ...(existing ?? {
          branchKey,
          summary: "",
          coverageNodeIds: [],
          coveragePathHash: "",
          lastCoveredNodeId: null,
          summarySchemaVersion: SUMMARY_SCHEMA_VERSION,
          compressionPromptVersion: COMPRESSION_PROMPT_VERSION,
          compressorProvider: normalizeModelId(selectedProviderId),
          compressorModel: normalizeModelId(selectedModelId),
          estimatedOriginalTokens: 0,
          estimatedSummaryTokens: 0,
          estimatedUncoveredTokens: 0,
          cacheStatus: undefined,
          error: null,
          createdAt: now,
        }),
        status: "pending",
        updatedAt: now,
      });

      try {
        const response = await compressAgentWorkspaceContext(agent.agent_id, {
          model_provider: selectedProviderId,
          model_name: selectedModelId,
          messages: activePath.map(serializeContextNode),
          pinned_node_ids: pinnedMessageIds,
          existing_summary: existing?.summary ?? null,
          prior_coverage_node_ids: existing?.coverageNodeIds ?? [],
          prior_coverage_path_hash: existing?.coveragePathHash ?? null,
          summary_schema_version: SUMMARY_SCHEMA_VERSION,
          compression_prompt_version: COMPRESSION_PROMPT_VERSION,
          compressor_provider: existing?.compressorProvider ?? selectedProviderId,
          compressor_model: existing?.compressorModel ?? selectedModelId,
        });
        const summary = workspaceCompressionSummary(branchKey, response);
        setTeamContextCompression(agent.slot_id, branchKey, summary);
        if (reason === "manual") {
          notifyFeedback({
            tone: "success",
            title: text("上下文已压缩", "Context compressed"),
            description: text(
              `已为“${agent.agent_name}”的 ${response.coverage_node_ids.length} 条消息生成摘要，预计从 ${Math.round(
                response.estimated_original_tokens,
              )} 标记压缩到 ${Math.round(response.estimated_summary_tokens)} 标记。`,
              `Summarized ${response.coverage_node_ids.length} messages for ${agent.agent_name}, reducing the estimated prompt from ${Math.round(
                response.estimated_original_tokens,
              )} to ${Math.round(response.estimated_summary_tokens)} tokens.`,
            ),
          });
        }
        return summary;
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        const failedAt = new Date().toISOString();
        setTeamContextCompression(agent.slot_id, branchKey, {
          ...(existing ?? {
            branchKey,
            summary: "",
            coverageNodeIds: [],
            coveragePathHash: "",
            lastCoveredNodeId: null,
            summarySchemaVersion: SUMMARY_SCHEMA_VERSION,
            compressionPromptVersion: COMPRESSION_PROMPT_VERSION,
            compressorProvider: normalizeModelId(selectedProviderId),
            compressorModel: normalizeModelId(selectedModelId),
            estimatedOriginalTokens: 0,
            estimatedSummaryTokens: 0,
            estimatedUncoveredTokens: 0,
            createdAt: failedAt,
          }),
          status: "error",
          cacheStatus: "error",
          error: message,
          updatedAt: failedAt,
        });
        if (reason === "manual") {
          notifyFeedback({
            tone: "error",
            title: text("上下文压缩失败", "Context compression failed"),
            description: message || text("请稍后重试。", "Please try again shortly."),
          });
        }
        return null;
      } finally {
        compressionInFlightRef.current.delete(branchKey);
      }
    },
    [
      contextCompressionsBySlotId,
      modelOptions,
      pinnedMessageIds,
      setTeamContextCompression,
      team,
      text,
    ],
  );

  return { clearTeamContextCompression, compressTeamContext };
}
