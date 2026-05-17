import type { ToolMention, ToolMetadata } from "../../tasks/api";

// Match standalone @tool tokens without treating email/user@host fragments as tools.
const TOOL_MENTION_PATTERN = /(?:^|[^\w@.-])@([\w-]+)(?!\.[A-Za-z0-9])(?=$|[^\w-])/g;
const LIST_FILES_INTENT_PATTERNS = [
  /列出(?:一下|下)?(?:当前|项目|工作区|目录)?文件/,
  /查看(?:一下|下)?(?:当前|项目|工作区|目录)?文件/,
  /(?:文件|目录)(?:清单|列表)/,
  /(?:项目|工作区|当前目录)文件/,
  /\blist\s+(?:the\s+)?(?:workspace\s+|project\s+|current\s+)?files\b/i,
  /\bshow\s+(?:the\s+)?(?:workspace\s+|project\s+|current\s+)?files\b/i,
  /\bfile\s+list\b/i,
  /\bdirectory\s+listing\b/i,
  /\bworkspace\s+files\b/i,
];
const KNOWN_TOOL_SOURCES = new Map<string, string>([
  ["read_file", "builtin"],
  ["list_files", "builtin"],
  ["write_file", "builtin"],
  ["run_shell", "builtin"],
  ["run_tests", "builtin"],
  ["network_request", "builtin"],
  ["git_command", "builtin"],
  ["mcp_context_search", "mcp"],
  ["mcp_artifact_put", "mcp"],
]);

export function extractToolMentions(
  content: string,
  tools: readonly ToolMetadata[],
): ToolMention[] {
  const names = new Set(
    [...content.matchAll(TOOL_MENTION_PATTERN)].map((match) => match[1]),
  );
  if (names.size === 0 && hasListFilesIntent(content, tools)) {
    names.add("list_files");
  }
  if (names.size === 0) return [];

  const registryNames = new Set(tools.map((tool) => tool.name));
  const registeredMentions = tools
    .filter((tool) => names.has(tool.name))
    .map((tool) => ({
      name: tool.name,
      source: tool.source,
      payload: { mention: `@${tool.name}` },
    }));
  const fallbackMentions = [...names]
    .filter((name) => !registryNames.has(name) && KNOWN_TOOL_SOURCES.has(name))
    .map((name) => ({
      name,
      source: KNOWN_TOOL_SOURCES.get(name) ?? null,
      payload: { mention: `@${name}` },
    }));
  return [...registeredMentions, ...fallbackMentions];
}

function hasListFilesIntent(content: string, tools: readonly ToolMetadata[]) {
  return (tools.length === 0 || tools.some((tool) => tool.name === "list_files"))
    && LIST_FILES_INTENT_PATTERNS.some((pattern) => pattern.test(content));
}
