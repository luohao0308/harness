/**
 * ChatRunSummary — small card rendered beneath the last assistant bubble
 * once that node reaches `state="done"` with a known `run_id`.
 *
 * Satisfies:
 *   - Req 7.5: short-hash badge + status badge + jump link to `/runs/:runId`.
 *   - Req 7 scope invariant: renders NO Approve/Reject/Modify controls, NO
 *     Plan DAG preview, NO Model Calls or Tool Call Runtime tables.
 *   - Req 9.1: copy flows through `useI18n().text(zh, en)`.
 *
 * Pure presentational component: stateless, no store access, no hooks beyond
 * `useI18n`. Visibility decisions live on the parent (`ChatMessageList`).
 */

import type { JSX } from "react";
import { Link } from "react-router-dom";
import { GitBranch } from "lucide-react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";

export type ChatRunSummaryProps = {
  /** Run identifier. Must be non-empty; parent guards this. */
  runId: string;
  /** Run status enum (e.g. "COMPLETED"). Renders a status badge when set. */
  runStatus?: string;
  /** ISO-8601 timestamp. Renders a localised timestamp when parseable. */
  runCreatedAt?: string;
};

export function ChatRunSummary({
  runId,
  runStatus,
  runCreatedAt,
}: ChatRunSummaryProps): JSX.Element {
  const { text, locale } = useI18n();
  const shortHash = runId.slice(0, 8);
  const createdLabel = formatLocalisedTimestamp(runCreatedAt, locale);
  const linkLabel = text("查看运行详情", "Open run detail");

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 shadow-sm">
      <GitBranch aria-hidden="true" className="h-3.5 w-3.5 text-slate-500" />
      <span className="font-mono text-slate-800">运行 {shortHash}</span>
      {runStatus && <Badge tone={statusTone(runStatus)}>{runStatus}</Badge>}
      {createdLabel && <span className="text-slate-500">{createdLabel}</span>}
      <div className="ml-auto">
        <Link to={`/runs/${runId}`} aria-label={linkLabel}>
          <Button variant="ghost">{linkLabel}</Button>
        </Link>
      </div>
    </div>
  );
}

function formatLocalisedTimestamp(value: string | undefined, locale: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  try {
    return date.toLocaleString(locale);
  } catch {
    return date.toLocaleString();
  }
}
