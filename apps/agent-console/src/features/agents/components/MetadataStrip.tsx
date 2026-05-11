/**
 * MetadataStrip — In · Out · $cost · TTFB · duration · Run hash row in the
 * Meta_Bar (Req 7.1–7.8 / Property P8).
 *
 * Pure React + `useI18n`. No `useState` / `useEffect`; does not read from
 * `useWorkspaceStore`. The container is always rendered (Req 7.4): when
 * `tail` is null or fields are missing, six `—` placeholders take their
 * place instead of hiding the strip.
 *
 * `formatMetadataField` is exported so Property P8 can exercise every
 * (value, field) combination without going through the DOM.
 */

import type { JSX } from "react";
import type { ConversationNode } from "../../../stores/workspaceStore";
import { useI18n } from "../../../lib/i18n";

export type MetadataStripProps = {
  /** Active_Path tail; `null` when the path is empty. */
  tail: ConversationNode | null;
  activeRunId: string | null;
  onOpenRunDetail: (runId: string) => void;
};

type MetadataField =
  | "input_tokens"
  | "output_tokens"
  | "cost_usd"
  | "cost_unavailable"
  | "ttfb_ms"
  | "duration_ms"
  | "run_id";

/**
 * Pure field-level formatter. TOTAL: never throws for any `value` shape.
 * The component-level `cost_unavailable === true → "N/A"` rule is applied
 * in the JSX wrapper below, not here.
 */
export function formatMetadataField(value: unknown, field: MetadataField): string {
  switch (field) {
    case "input_tokens":
    case "output_tokens":
      return typeof value === "number" ? String(value) : "—";
    case "cost_usd":
      if (value === undefined || value === null) return "—";
      if (typeof value === "string" && value !== "") {
        return "$" + Number(value).toFixed(4);
      }
      return "—";
    case "cost_unavailable":
      return value === true ? "N/A" : "—";
    case "ttfb_ms":
    case "duration_ms":
      return typeof value === "number" ? `${value}ms` : "—";
    case "run_id":
      return typeof value === "string" && value.length > 0 ? value.slice(0, 8) : "—";
  }
}

export function MetadataStrip({
  tail,
  activeRunId,
  onOpenRunDetail,
}: MetadataStripProps): JSX.Element {
  const { text } = useI18n();

  // Component-level wrapper for the special `cost_unavailable` signal
  // (Req 7.1 / Req 7.8): when the upstream run reports that cost is not
  // available, render "N/A" instead of "—".
  const costLabel =
    tail?.metadata.cost_unavailable === true
      ? "N/A"
      : formatMetadataField(tail?.metadata.cost_usd, "cost_usd");

  return (
    <div
      className="flex items-center gap-3 overflow-x-auto text-xs text-slate-500"
      aria-label={text("元数据", "Metadata")}
    >
      <span>
        {text("输入", "In")} {formatMetadataField(tail?.metadata.input_tokens, "input_tokens")}
      </span>
      <span aria-hidden="true">·</span>
      <span>
        {text("输出", "Out")} {formatMetadataField(tail?.metadata.output_tokens, "output_tokens")}
      </span>
      <span aria-hidden="true">·</span>
      <span>
        {text("成本", "Cost")} {costLabel}
      </span>
      <span aria-hidden="true">·</span>
      <span>TTFB {formatMetadataField(tail?.metadata.ttfb_ms, "ttfb_ms")}</span>
      <span aria-hidden="true">·</span>
      <span>
        {text("耗时", "Duration")} {formatMetadataField(tail?.metadata.duration_ms, "duration_ms")}
      </span>
      <span aria-hidden="true">·</span>
      <span>
        {text("Run", "Run")}{" "}
        {activeRunId !== null && activeRunId.length > 0 ? (
          <button
            type="button"
            onClick={() => onOpenRunDetail(activeRunId)}
            className="underline hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-1 rounded"
          >
            {activeRunId.slice(0, 8)}
          </button>
        ) : (
          "—"
        )}
      </span>
    </div>
  );
}
