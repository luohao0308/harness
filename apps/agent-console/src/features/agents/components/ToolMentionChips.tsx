/**
 * ToolMentionChips — up to 5 tool-name chips that insert `@tool-name ` into
 * the composer draft (Req 6.5 / 6.9).
 *
 * Pure presentational component:
 *   - Renders at most the first 5 tools in `tools` as pill-shaped
 *     `<button type="button">` chips labelled `@{tool.name}`. Clicking a chip
 *     invokes `onInsertMention(tool.name)`; the parent (`ComposerToolbar`)
 *     is responsible for appending `@{name} ` into `useWorkspaceStore.draft`.
 *   - When `tools.length === 0` the component renders a bilingual "no tools"
 *     notice so the toolbar slot is never visually empty (Req 6.9).
 *
 * No hooks beyond `useI18n`; does not read the workspace store. `ToolMetadata`
 * is imported as `type` only — this component never touches `/tasks` runtime.
 */

import type { JSX } from "react";

import { useI18n } from "../../../lib/i18n";
import type { ToolMetadata } from "../../tasks/api";

const MAX_VISIBLE_TOOLS = 5;

export type ToolMentionChipsProps = {
  tools: ToolMetadata[];
  onInsertMention: (toolName: string) => void;
};

export function ToolMentionChips({
  tools,
  onInsertMention,
}: ToolMentionChipsProps): JSX.Element {
  const { text } = useI18n();

  if (tools.length === 0) {
    return (
      <span className="text-xs text-slate-400">
        {text("无可用工具", "No tools")}
      </span>
    );
  }

  const visible = tools.slice(0, MAX_VISIBLE_TOOLS);

  return (
    <div
      className="flex flex-wrap items-center gap-1"
      aria-label={text("工具提及", "Tool mentions")}
    >
      {visible.map((tool) => (
        <button
          key={tool.name}
          type="button"
          onClick={() => onInsertMention(tool.name)}
          className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700 transition-colors hover:bg-slate-50"
          title={tool.description || tool.name}
        >
          @{tool.name}
        </button>
      ))}
    </div>
  );
}
