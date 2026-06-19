export type WorkspaceRunReturnTarget = {
  agentId: string;
  conversationId?: string | null;
};

const WORKSPACE_RETURN_TARGET_STORAGE_KEY = "harness.workspace.run-return-target";
let inMemoryWorkspaceReturnTarget: string | null = null;

export function workspaceReturnPath({
  agentId,
  conversationId,
}: WorkspaceRunReturnTarget): string {
  const base = `/agents/${encodeURIComponent(agentId || "default")}/workspace`;
  const conversation = conversationId?.trim();
  if (!conversation) return base;
  const params = new URLSearchParams();
  params.set("conversation_id", conversation);
  return `${base}?${params.toString()}`;
}

export function runDetailPath(
  runId: string,
  target: WorkspaceRunReturnTarget,
  hash = "",
): string {
  const params = new URLSearchParams();
  params.set("return_to", workspaceReturnPath(target));
  const conversation = target.conversationId?.trim();
  if (conversation) params.set("conversation_id", conversation);
  const fragment = hash.startsWith("#") ? hash : hash ? `#${hash}` : "";
  return `/runs/${encodeURIComponent(runId)}?${params.toString()}${fragment}`;
}

export function saveWorkspaceReturnTarget(
  target: WorkspaceRunReturnTarget,
  runId?: string | null,
): void {
  try {
    const payload = {
      runId: runId?.trim() || null,
      agentId: target.agentId,
      conversationId: target.conversationId?.trim() || null,
    };
    const serialized = JSON.stringify(payload);
    if (typeof sessionStorage === "undefined") {
      inMemoryWorkspaceReturnTarget = serialized;
      return;
    }
    sessionStorage.setItem(WORKSPACE_RETURN_TARGET_STORAGE_KEY, serialized);
  } catch {
    inMemoryWorkspaceReturnTarget = JSON.stringify({
      runId: runId?.trim() || null,
      agentId: target.agentId,
      conversationId: target.conversationId?.trim() || null,
    });
  }
}

export function readWorkspaceReturnTarget(runId?: string | null): WorkspaceRunReturnTarget | null {
  try {
    const raw =
      typeof sessionStorage === "undefined"
        ? inMemoryWorkspaceReturnTarget
        : sessionStorage.getItem(WORKSPACE_RETURN_TARGET_STORAGE_KEY) ?? inMemoryWorkspaceReturnTarget;
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return null;
    const candidate = parsed as {
      runId?: unknown;
      agentId?: unknown;
      conversationId?: unknown;
    };
    if (
      typeof runId === "string" &&
      runId.trim() &&
      typeof candidate.runId === "string" &&
      candidate.runId !== runId
    ) {
      return null;
    }
    if (typeof candidate.agentId !== "string" || candidate.agentId.trim() === "") return null;
    const conversationId =
      typeof candidate.conversationId === "string" && candidate.conversationId.trim()
        ? candidate.conversationId.trim()
        : null;
    return {
      agentId: candidate.agentId.trim(),
      conversationId,
    };
  } catch {
    return null;
  }
}

export function clearWorkspaceReturnTarget(): void {
  try {
    inMemoryWorkspaceReturnTarget = null;
    if (typeof sessionStorage === "undefined") return;
    sessionStorage.removeItem(WORKSPACE_RETURN_TARGET_STORAGE_KEY);
  } catch {
    inMemoryWorkspaceReturnTarget = null;
  }
}
