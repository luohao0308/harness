export type ChangeReviewState =
  | "ready"
  | "no-workspace"
  | "not-repository"
  | "git-unavailable"
  | "error";

export type ChangeFile = {
  path: string;
  previousPath?: string | null;
  indexStatus: string;
  worktreeStatus: string;
  staged: boolean;
  unstaged: boolean;
  untracked: boolean;
  conflicted: boolean;
};

export type ChangeReviewStatus = {
  state: ChangeReviewState;
  files: ChangeFile[];
  message?: string | null;
};

export type DiffHunk = {
  id: string;
  header: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: string[];
};

export type DiffSection = {
  mode: "staged" | "worktree";
  kind: "text" | "binary" | "conflict" | "empty" | "too-large";
  headerLines: string[];
  hunks: DiffHunk[];
  canStage: boolean;
  canUnstage: boolean;
  canRevert: boolean;
  message?: string | null;
};

export type ChangeDiff = {
  path: string;
  previewToken: string;
  expiresAt: string;
  sections: DiffSection[];
};

export type ChangeMutationAction = "stage" | "unstage" | "revert";

export type ChangeAuditContext = {
  taskId?: string;
  runId?: string;
  approvalId?: string;
};

export type ChangeMutationInput = {
  previewToken: string;
  hunkIds: string[];
  action: ChangeMutationAction;
  auditContext?: ChangeAuditContext;
};

export type ChangeMutationResult = {
  action: ChangeMutationAction;
  path: string;
  status: string;
  updatedAt: string;
  auditId?: string | null;
  eventId?: string | null;
};

export type DesktopChangeReviewApi = {
  getStatus: () => Promise<ChangeReviewStatus>;
  getDiff: (path: string) => Promise<ChangeDiff>;
  mutate: (input: ChangeMutationInput) => Promise<ChangeMutationResult>;
};
