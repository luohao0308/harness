/**
 * ChatWelcomeState — the empty-state onboarding card shown when
 * `Active_Path` has zero conversation nodes.
 *
 * Satisfies:
 *   - Req 8.1–8.3: shows the agent name, model label, a ≤3-line intro, and
 *     3–5 example prompts sourced from {@link EXAMPLE_PROMPTS}.
 *   - Req 9.1: all copy flows through `useI18n().text(zh, en)`.
 *   - Req 9.3: prompt tiles are real `<button>` elements with focus-visible
 *     rings so keyboard navigation lands on them.
 *
 * Pure presentational component: stateless, no store access, no hooks beyond
 * `useI18n`. Clicking a prompt invokes the parent-supplied callback which is
 * responsible for filling the composer draft and focusing the textarea.
 */

import type { JSX } from "react";
import { Sparkles } from "lucide-react";

import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import { EXAMPLE_PROMPTS } from "../lib/examplePrompts";

export type ChatWelcomeStateProps = {
  /** Human-readable agent name (falls back to agentId in the parent). */
  agentName: string;
  /** Human-readable model label (e.g. "openai / gpt-4o-mini"). */
  modelLabel: string;
  /** Invoked when the user picks an example prompt. */
  onPickPrompt: (prompt: string) => void;
};

export function ChatWelcomeState({
  agentName,
  modelLabel,
  onPickPrompt,
}: ChatWelcomeStateProps): JSX.Element {
  const { text } = useI18n();
  const intro = text(
    "这是 Harness 的 Agent Workspace。像 Claude Code / Codex 一样和 Agent 对话，工具调用与运行细节会同步到右侧 Inspector 或 Run 详情页。",
    "This is Harness's Agent Workspace. Chat with the agent like Claude Code or Codex — tool calls and run details stream to the Inspector drawer or Run Detail page.",
  );

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-5 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <header className="flex items-start gap-3">
        <div
          aria-hidden="true"
          className="mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-slate-950 text-white"
        >
          <Sparkles className="h-5 w-5" />
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-xl font-semibold text-slate-900">{agentName}</h2>
          <p className="mt-0.5 truncate text-xs text-slate-500">{modelLabel}</p>
        </div>
      </header>

      <p className="line-clamp-3 text-sm leading-6 text-slate-600">{intro}</p>

      <div className="flex flex-col gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-400">
          {text("试试这些提示", "Try these prompts")}
        </span>
        <div className="flex flex-col gap-2">
          {EXAMPLE_PROMPTS.map((prompt) => {
            const label = text(prompt.zh, prompt.en);
            return (
              <button
                key={prompt.id}
                type="button"
                onClick={() => onPickPrompt(label)}
                className={cn(
                  "rounded-xl border border-slate-200 bg-white px-3 py-2 text-left text-sm text-slate-700",
                  "hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
                )}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}
