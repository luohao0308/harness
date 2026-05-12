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
  const headline = text("我们先从哪里开始呢？", "Where should we start?");

  return (
    <section className="mx-auto flex w-full max-w-3xl flex-col items-center gap-7 text-center">
      <header className="flex max-w-2xl flex-col items-center">
        <p className="mb-3 text-xs font-medium text-slate-400">
          {agentName} · {modelLabel}
        </p>
        <h2 className="text-2xl font-semibold tracking-normal text-slate-900 sm:text-3xl">
          {headline}
        </h2>
      </header>

      <div className="flex w-full flex-col items-center gap-3">
        <div className="flex max-w-2xl flex-wrap justify-center gap-2">
          {EXAMPLE_PROMPTS.map((prompt) => {
            const label = text(prompt.zh, prompt.en);
            return (
              <button
                key={prompt.id}
                type="button"
                onClick={() => onPickPrompt(label)}
                className={cn(
                  "rounded-full border border-slate-200 bg-white px-3 py-2 text-sm text-slate-600 shadow-sm",
                  "hover:bg-slate-50 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400",
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
