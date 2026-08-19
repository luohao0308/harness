import {
  listAgentProjectKnowledgeIndexes,
  listAgents,
  syncAgentProjectKnowledgeIndex,
  type ProjectKnowledgeIndex,
  type ProjectKnowledgeSyncPayload,
} from "../features/tasks/api";

const PROJECT_SYNC_INTERVAL_MS = 30_000;
const PROJECT_SYNC_DEBOUNCE_MS = 750;

export function projectSnapshotToSyncPayload(
  snapshot: DesktopProjectKnowledgeSnapshot,
  desktopProfileId: string,
): ProjectKnowledgeSyncPayload {
  return {
    schema_version: snapshot.schemaVersion,
    default_ignore_version: snapshot.defaultIgnoreVersion,
    desktop_profile_id: desktopProfileId,
    root_identity: snapshot.rootIdentity,
    snapshot_generation: snapshot.snapshotGeneration ?? 1,
    snapshot_cursor: snapshot.snapshotCursor,
    complete: snapshot.complete,
    truncated: snapshot.truncated,
    truncation_reason: snapshot.truncationReason,
    files: snapshot.files.map((file) => ({
      relative_path: file.relativePath,
      status: file.status,
      content: file.content,
      content_sha256: file.contentSha256,
      size_bytes: file.sizeBytes,
      modified_at: file.modifiedAt,
      mime_type: file.mimeType,
      skip_reason: file.skipReason,
    })),
    errors: snapshot.errors,
    scanned_files: snapshot.scannedFiles,
    indexed_files: snapshot.indexedFiles,
    total_bytes: snapshot.totalBytes,
    started_at: snapshot.startedAt,
    completed_at: snapshot.completedAt,
  };
}

export async function scanAndSyncProjectKnowledgeIndex(
  agentId: string,
  index: ProjectKnowledgeIndex,
  isCurrent: () => boolean = () => true,
): Promise<ProjectKnowledgeIndex> {
  const profileList = await requireDesktopProfileList();
  if (profileList.activeProfileId !== index.desktop_profile_id) {
    throw new Error("请先切换到该项目索引绑定的 Desktop Profile");
  }
  const scan = window.desktopApi?.file?.scanProjectKnowledge;
  if (!scan) throw new Error("当前环境不支持项目知识扫描");
  const getWorkspaceRoot = window.desktopApi?.file?.getWorkspaceRoot;
  const rootBeforeScan = getWorkspaceRoot ? await getWorkspaceRoot() : null;
  const snapshot = await scan({ ignorePatterns: index.ignore_patterns });
  if (snapshot.rootIdentity !== index.root_identity) {
    throw new Error("当前工作区与项目知识索引绑定目录不一致");
  }
  const [currentProfileList, rootAfterScan] = await Promise.all([
    requireDesktopProfileList(),
    getWorkspaceRoot ? getWorkspaceRoot() : Promise.resolve(null),
  ]);
  if (
    !isCurrent()
    || currentProfileList.activeProfileId !== profileList.activeProfileId
  ) {
    throw new Error("扫描期间 Desktop Profile 已切换，已取消本次同步");
  }
  if (rootBeforeScan?.rootPath !== rootAfterScan?.rootPath) {
    throw new Error("扫描期间项目目录已切换，已取消本次同步");
  }
  return syncAgentProjectKnowledgeIndex(
    agentId,
    index.id,
    projectSnapshotToSyncPayload(snapshot, profileList.activeProfileId),
  );
}

export function installProjectKnowledgeSync(): () => void {
  const desktopApi = window.desktopApi;
  if (
    !desktopApi?.file?.scanProjectKnowledge
    || !desktopApi.profile?.list
  ) {
    return () => undefined;
  }

  let disposed = false;
  let running: Promise<void> | null = null;
  let rerunRequested = false;
  let debounceTimer: number | null = null;
  let contextGeneration = 0;

  const runAll = async (): Promise<void> => {
    const runGeneration = contextGeneration;
    const profileList = await requireDesktopProfileList();
    const agents = await listAgents();
    for (const agent of agents.items) {
      const page = await listAgentProjectKnowledgeIndexes(agent.id);
      const candidates = page.items.filter(
        (index) =>
          index.desktop_profile_id === profileList.activeProfileId
          && (index.status === "ACTIVE" || index.status === "ERROR"),
      );
      for (const index of candidates) {
        if (disposed) return;
        try {
          await scanAndSyncProjectKnowledgeIndex(
            agent.id,
            index,
            () => runGeneration === contextGeneration,
          );
        } catch {
          // The API persists scan/sync errors when a snapshot exists. Missing roots,
          // profile switches, and temporary auth failures retry on the next cycle.
          if (runGeneration !== contextGeneration) return;
        }
      }
    }
  };

  const runCoalesced = (): Promise<void> => {
    if (running) {
      rerunRequested = true;
      return running;
    }
    running = runAll()
      .catch(() => undefined)
      .finally(() => {
        running = null;
        if (rerunRequested && !disposed) {
          rerunRequested = false;
          void runCoalesced();
        }
      });
    return running;
  };

  const schedule = () => {
    if (disposed) return;
    if (debounceTimer !== null) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      debounceTimer = null;
      void runCoalesced();
    }, PROJECT_SYNC_DEBOUNCE_MS);
  };

  void desktopApi.file.startWatch?.().catch(() => undefined);
  const unsubscribeFile = desktopApi.file.onChange?.(schedule);
  const unsubscribeProfile = desktopApi.events?.onProfileChanged?.(() => {
    contextGeneration += 1;
    schedule();
  });
  const interval = window.setInterval(() => void runCoalesced(), PROJECT_SYNC_INTERVAL_MS);
  schedule();

  return () => {
    disposed = true;
    if (debounceTimer !== null) window.clearTimeout(debounceTimer);
    window.clearInterval(interval);
    unsubscribeFile?.();
    unsubscribeProfile?.();
  };
}

async function requireDesktopProfileList(): Promise<{
  activeProfileId: string;
  profiles: DesktopProfile[];
}> {
  const listProfiles = window.desktopApi?.profile?.list;
  if (!listProfiles) throw new Error("当前环境不支持 Desktop Profile");
  return listProfiles();
}
