import type { WorkspaceMode } from "../../../agents/lib/types";
import type { ContextCompressionSummary } from "../../../agents/lib/contextCompression";
import type {
  AgentMessage,
  Team,
  TeamMailboxMessage,
} from "../../../tasks/api";
import type { ConversationNode } from "../../../../stores/workspaceStore";

export type TeamComposerState = { draft: string; target?: string; mode?: WorkspaceMode };
export type TeamComposerStateUpdater =
  | TeamComposerState
  | ((current: TeamComposerState) => TeamComposerState);
export type ComposerState = Record<string, TeamComposerState>;
export type TeamBottomPanel = "settings" | "model" | "mcp" | null;
export type TextFn = (zh: string, en: string) => string;
export type TeamModelChangeHandler = (slotId: string, providerId: string, modelId: string) => void;
export const MAX_TEAM_ATTACHMENT_TEXT_BYTES = 120_000;

export type TeamPageEnvelope = { items: Team[]; next_cursor: string | null };
export type TeamMessageEntry = { kind: "session"; message: AgentMessage } | { kind: "mailbox"; message: TeamMailboxMessage };
export type TeamConversationEntry = {
  node: ConversationNode;
  target: string;
  runStatus?: string;
  runCreatedAt?: string;
};
export type TeamContextCompressions = Record<string, Record<string, ContextCompressionSummary>>;
export type TeamBranchGroup = {
  anchorUserId: string;
  anchorContent: string;
  branchNodeIds: string[];
  hiddenUserNodeIds: string[];
  activeNodeId: string;
};
export type TeamBranchGroupsBySlot = Record<string, Record<string, TeamBranchGroup>>;
export type PendingSend = {
  id: string;
  key: string;
  sourceSlotId: string;
  target: string;
  content: string;
  files: string[];
  mode: WorkspaceMode;
  recipientSlotIds: string[];
};
export type StreamingWake = {
  slotId: string;
  content: string;
  error?: string;
};

export type SettledWakeCutoffs = Record<string, number>;
