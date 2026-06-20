export type ConsoleNavIconKey =
  | "activity"
  | "audit"
  | "bot"
  | "box"
  | "brain"
  | "brainCircuit"
  | "dashboard"
  | "database"
  | "evals"
  | "gauge"
  | "help"
  | "key"
  | "knowledge"
  | "network"
  | "runs"
  | "settings"
  | "shield"
  | "store"
  | "tools"
  | "users";

export type ConsoleNavItem = {
  to: string;
  label: string;
  iconKey: ConsoleNavIconKey;
};

export type ConsoleNavGroup = {
  id: string;
  label: string;
  iconKey: ConsoleNavIconKey;
  children: ConsoleNavItem[];
};

export type ConsoleNavEntry = ConsoleNavItem | ConsoleNavGroup;

export const consoleNavEntries = [
  { to: "/", label: "Dashboard", iconKey: "dashboard" },
  { to: "/agents", label: "智能体", iconKey: "bot" },
  { to: "/teams", label: "团队", iconKey: "network" },
  { to: "/runs", label: "运行历史", iconKey: "runs" },
  {
    id: "agent-marketplace",
    label: "专家与子代理",
    iconKey: "store",
    children: [
      { to: "/subagents", label: "子代理", iconKey: "bot" },
      { to: "/subagent-specialists", label: "专家库", iconKey: "brainCircuit" },
      { to: "/subagent-marketplace", label: "专家市场", iconKey: "store" },
    ],
  },
  { to: "/knowledge", label: "知识库", iconKey: "knowledge" },
  {
    id: "tools-capabilities",
    label: "工具与能力",
    iconKey: "tools",
    children: [
      { to: "/tools", label: "工具市场", iconKey: "tools" },
      { to: "/tools/config", label: "工具配置", iconKey: "settings" },
      { to: "/sandboxes", label: "沙箱", iconKey: "box" },
    ],
  },
  { to: "/observability", label: "观测", iconKey: "activity" },
  { to: "/token-savings", label: "Token 节省", iconKey: "gauge" },
  { to: "/evals", label: "评测", iconKey: "evals" },
  {
    id: "settings",
    label: "设置",
    iconKey: "settings",
    children: [
      { to: "/settings/policies", label: "策略", iconKey: "shield" },
      { to: "/settings/models", label: "模型", iconKey: "brain" },
      { to: "/settings/secrets", label: "密钥库", iconKey: "key" },
      { to: "/settings/users", label: "用户", iconKey: "users" },
      { to: "/settings/api-keys", label: "API Keys", iconKey: "key" },
      { to: "/settings/audit", label: "审计", iconKey: "audit" },
      { to: "/settings/data-management", label: "数据", iconKey: "database" },
    ],
  },
  { to: "/help", label: "帮助", iconKey: "help" },
] satisfies ConsoleNavEntry[];

export function isConsoleNavGroup(entry: ConsoleNavEntry): entry is ConsoleNavGroup {
  return "children" in entry;
}

export function flattenConsoleNavEntries(entries: readonly ConsoleNavEntry[] = consoleNavEntries) {
  return entries.flatMap((entry) => (isConsoleNavGroup(entry) ? entry.children : [entry]));
}
