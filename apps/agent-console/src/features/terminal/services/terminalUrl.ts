export function resolveTerminalWebSocketBaseUrl(options: {
  localRuntime: boolean;
  pageOrigin: string;
  configuredUrl?: string;
}): string {
  if (options.localRuntime) {
    const url = new URL("/ws/terminal", options.pageOrigin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }
  return options.configuredUrl?.trim() || "ws://localhost:8000/ws/terminal";
}
