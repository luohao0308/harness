import type { ToolMention, ToolMetadata } from "../../tasks/api";

// Match standalone @tool tokens without treating email/user@host fragments as tools.
const TOOL_MENTION_PATTERN = /(?:^|[^\w@.-])@([\w-]+)(?!\.[A-Za-z0-9])(?=$|[^\w-])/g;

export function extractToolMentions(
  content: string,
  tools: readonly ToolMetadata[],
): ToolMention[] {
  const names = new Set(
    [...content.matchAll(TOOL_MENTION_PATTERN)].map((match) => match[1]),
  );
  if (names.size === 0) return [];

  return tools
    .filter((tool) => names.has(tool.name))
    .map((tool) => ({
      name: tool.name,
      source: tool.source,
      payload: { mention: `@${tool.name}` },
    }));
}
