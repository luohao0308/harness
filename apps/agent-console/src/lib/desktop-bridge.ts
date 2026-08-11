type DesktopRoutePayload = {
  route: string;
  source: "deep-link" | "notification" | "menu" | "shortcut" | "ipc";
};

type DesktopFileEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
  sizeBytes: number;
  modifiedAt: string;
  depth: number;
  mimeType: string | null;
};

type DesktopFileChangeEvent = {
  rootPath: string;
  path: string;
  eventType: "change" | "rename";
  kind: "file" | "directory" | "unknown";
  changedAt: string;
};

type DesktopFileReadResult = {
  path: string;
  content: string;
  sizeBytes: number;
  totalSizeBytes: number;
  mimeType: string;
  truncated: boolean;
  editable: boolean;
};

type DesktopFileWriteResult = {
  path: string;
  bytesWritten: number;
  updatedAt: string;
};

type DesktopFileWatchState = {
  rootPath: string | null;
  watching: boolean;
};

type DesktopFileListResult = {
  rootPath: string | null;
  entries: DesktopFileEntry[];
  truncated: boolean;
};

type DesktopRouter = {
  navigate: (route: string) => void | Promise<void>;
};

type DesktopApi = {
  system?: {
    getPendingRoute?: () => Promise<DesktopRoutePayload | null>;
  };
  events?: {
    onOpenRoute?: (callback: (payload: DesktopRoutePayload) => void) => () => void;
  };
  file?: {
    selectWorkspaceRoot?: () => Promise<DesktopFileWatchState | null>;
    getWorkspaceRoot?: () => Promise<DesktopFileWatchState>;
    setWorkspaceRoot?: (rootPath: string | null) => Promise<DesktopFileWatchState>;
    startWatch?: () => Promise<DesktopFileWatchState>;
    stopWatch?: () => Promise<DesktopFileWatchState>;
    listFiles?: (options?: {
      path?: string;
      maxDepth?: number;
      maxEntries?: number;
    }) => Promise<DesktopFileListResult>;
    readFile?: (path: string) => Promise<DesktopFileReadResult>;
    writeFile?: (path: string, content: string) => Promise<DesktopFileWriteResult>;
    onChange?: (callback: (event: DesktopFileChangeEvent) => void) => (() => void);
  };
};

const DESKTOP_ROUTE_BASE_URL = "https://agentharness.local";

export function isDesktopRuntime(): boolean {
  return typeof window !== "undefined" && Boolean(window.desktopApi);
}

export function installDesktopBridge(router: DesktopRouter): () => void {
  const desktopApi = window.desktopApi as DesktopApi | undefined;
  if (!desktopApi) return () => undefined;

  let disposed = false;

  const navigateToPayload = (payload: DesktopRoutePayload | null) => {
    if (disposed || !payload) return;
    const route = normalizeDesktopRoute(payload.route);
    void router.navigate(route);
  };

  void desktopApi.system?.getPendingRoute?.().then(navigateToPayload).catch(() => undefined);

  const unsubscribe = desktopApi.events?.onOpenRoute?.(navigateToPayload);

  return () => {
    disposed = true;
    unsubscribe?.();
  };
}

function normalizeDesktopRoute(route: string): string {
  const trimmed = route.trim();
  if (!trimmed || trimmed.startsWith("//")) return "/";

  try {
    const url = new URL(trimmed, DESKTOP_ROUTE_BASE_URL);
    return `${url.pathname || "/"}${url.search}${url.hash}`;
  } catch {
    return "/";
  }
}
