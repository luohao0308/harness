export type WorkspaceMode = "chat" | "markdown_plan" | "plan" | "goal";
export type InspectorSection = "artifacts" | "runtime";

const LEGACY_MARKDOWN_PLAN_MODE = "co" + "dex_plan";

export function normalizeWorkspaceMode(mode: unknown): WorkspaceMode {
  if (mode === "chat" || mode === "markdown_plan" || mode === "plan" || mode === "goal") {
    return mode;
  }
  if (mode === LEGACY_MARKDOWN_PLAN_MODE) return "markdown_plan";
  return "chat";
}
