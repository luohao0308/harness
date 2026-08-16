export type LocalRuntimeModelState = "setup_required" | "configured" | "healthy" | "error";

export type LocalRuntimeModelStatus = {
  state: LocalRuntimeModelState;
  provider: string;
  model: string;
  base_url: string;
  secret_storage: "persistent" | "session" | "unavailable";
  message?: string | null;
};

const WEB_BOOTSTRAP_FRAGMENT_KEY = "bootstrap";

export function isLocalRuntimeProfile(): boolean {
  return import.meta.env.VITE_RUNTIME_PROFILE === "local";
}

export function isLocalWebExtension(): boolean {
  return isLocalRuntimeProfile() && typeof window !== "undefined" && !window.desktopApi;
}

export function getDesktopLocalRuntimeApi() {
  return typeof window === "undefined" ? undefined : window.desktopApi?.localRuntime;
}

export async function initializeLocalRuntimeSession(fetchImpl: typeof fetch = fetch): Promise<void> {
  if (!isLocalRuntimeProfile() || typeof window === "undefined") return;

  const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const bootstrapToken = fragment.get(WEB_BOOTSTRAP_FRAGMENT_KEY)?.trim();
  if (!bootstrapToken) return;

  fragment.delete(WEB_BOOTSTRAP_FRAGMENT_KEY);
  const remainingFragment = fragment.toString();
  window.history.replaceState(
    window.history.state,
    "",
    `${window.location.pathname}${window.location.search}${remainingFragment ? `#${remainingFragment}` : ""}`,
  );

  const response = await fetchImpl("/api/local-runtime/web/bootstrap/exchange", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token: bootstrapToken }),
  });
  if (!response.ok) {
    throw new Error(`Web Extension bootstrap failed (${response.status})`);
  }
}
