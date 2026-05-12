/**
 * InspectorDrawer — the on-demand side panel for Workspace.
 *
 * Satisfies:
 *   - Req 7.1–7.8 (scope invariant P4): the chat surface never renders the
 *     Approvals action row, Plan DAG canvas, Model Calls table, Tool Call
 *     Runtime table, or Save/Run/Replay eval buttons. This drawer exposes
 *     only LINKS back to `/runs/:runId` anchors, `/observability`, `/evals`.
 *   - Req 9.3, 9.5: dialog role with aria-modal, aria-labelledby, Esc close,
 *     focus returns to the trigger button that opened the drawer.
 *   - Design §Inspector Drawer: artifacts and runtime sections render when
 *     `section` matches; runtime shows a
 *     pending-approval banner plus a LinkGroup.
 *
 * Intentionally: no Approve / Reject / Modify controls, no Plan DAG canvas,
 * no Model Calls or Tool Runtime tables, no "save as eval case" /
 * "Run Evals" / "Replay Run" buttons. All such destinations live in
 * `/runs/:runId` (see the LinkGroup inside the runtime section).
 */

import type { JSX } from "react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ExternalLink, FileCode2, Shield, X } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { useI18n } from "../../../lib/i18n";
import { cn } from "../../../lib/utils";
import type { ConversationArtifact } from "../../../stores/workspaceStore";
import type { InspectorSection } from "../lib/types";

export type UsageSummary = {
  inputTokens: number;
  outputTokens: number;
  costUsd: string;
  durationMs: number;
  modelCalls: number;
  toolCalls: number;
};

export type InspectorDrawerProps = {
  /** Which section to render; drawer is closed when `null`. */
  section: InspectorSection | null;
  /** Active Run id for deep-link buttons; disabled state when null. */
  activeRunId: string | null;
  /** Number of approvals whose status is PENDING. Drives the runtime banner. */
  pendingApprovalCount: number;
  /** Parent is expected to have already capped this to the most recent 10. */
  artifacts: ConversationArtifact[];
  /** Callback to close the drawer (triggered by backdrop, close button, Esc). */
  onClose: () => void;
};

export function InspectorDrawer({
  section,
  activeRunId,
  pendingApprovalCount,
  artifacts,
  onClose,
}: InspectorDrawerProps): JSX.Element | null {
  const { text } = useI18n();
  // Remember the element that had focus when the drawer opened so we can
  // restore it on close (Req 9.3). Falls back to document.body when the
  // trigger is no longer in the DOM.
  const lastTriggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (section === null) {
      const last = lastTriggerRef.current;
      lastTriggerRef.current = null;
      if (last && typeof last.focus === "function") {
        last.focus();
      }
      return;
    }
    const active = document.activeElement;
    lastTriggerRef.current = active instanceof HTMLElement ? active : null;

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [section, onClose]);

  if (section === null) return null;

  const title =
    section === "artifacts"
      ? text("产物 / 预览", "Artifacts / Preview")
      : text("运行时链接", "Runtime links");

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-40 cursor-default bg-slate-950/10"
        aria-label={text("关闭面板", "Close inspector")}
        onClick={onClose}
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-labelledby="inspector-title"
        className="fixed inset-y-14 right-0 z-50 w-[420px] overflow-y-auto border-l border-slate-200 bg-white shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div>
            <div id="inspector-title" className="text-sm font-semibold text-slate-950">
              {title}
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {text(
                "按需展开的运行观察面板，详细操作请前往 Run 详情。",
                "On-demand inspector. Detailed actions live in Run Detail.",
              )}
            </div>
          </div>
          <Button
            variant="ghost"
            className="h-8 w-8 px-0"
            onClick={onClose}
            aria-label={text("关闭", "Close")}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-4 p-4">
          {section === "artifacts" && <ArtifactsSection artifacts={artifacts} />}
          {section === "runtime" && (
            <RuntimeSection
              activeRunId={activeRunId}
              pendingApprovalCount={pendingApprovalCount}
            />
          )}
        </div>
      </aside>
    </>
  );
}

// ---------------------------------------------------------------------------
// Artifacts section — most-recent 10 with preview pane.
// ---------------------------------------------------------------------------

function ArtifactsSection({ artifacts }: { artifacts: ConversationArtifact[] }): JSX.Element {
  const { text } = useI18n();
  // Defensive cap in case the parent passes more than ten; the contract is
  // that `artifacts` is already `.slice(-10)`, but we do not rely on it.
  const recent = artifacts.slice(-10);
  const [selectedId, setSelectedId] = useState<string | null>(recent[recent.length - 1]?.id ?? null);
  const selected = recent.find((artifact) => artifact.id === selectedId) ?? recent[recent.length - 1];

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <SectionHeader
        icon={<FileCode2 className="h-4 w-4" />}
        title={text("产物 / 预览", "Artifacts / Preview")}
        aside={String(recent.length)}
      />
      <div className="grid grid-cols-[140px_1fr] border-t border-slate-100">
        <div className="max-h-80 overflow-auto border-r border-slate-100 p-2">
          {recent.length === 0 ? (
            <EmptyState label={text("暂无产物", "No artifacts yet")} />
          ) : (
            recent.map((artifact) => {
              const active = selected?.id === artifact.id;
              return (
                <button
                  key={artifact.id}
                  type="button"
                  onClick={() => setSelectedId(artifact.id)}
                  className={cn(
                    "mb-1 flex w-full items-center gap-1 rounded px-2 py-1 text-left text-xs focus-visible:ring-2 focus-visible:ring-slate-400",
                    active ? "bg-slate-900 text-white" : "hover:bg-slate-50 text-slate-700",
                  )}
                >
                  <FileCode2 aria-hidden="true" className="h-3 w-3" />
                  <span className="truncate">{artifact.name}</span>
                </button>
              );
            })
          )}
        </div>
        <div className="max-h-80 overflow-auto p-3">
          {selected ? (
            <ArtifactPreview artifact={selected} />
          ) : (
            <EmptyState label={text("选择左侧产物以预览", "Pick an artifact to preview")} />
          )}
        </div>
      </div>
    </section>
  );
}

function ArtifactPreview({ artifact }: { artifact: ConversationArtifact }): JSX.Element {
  const content =
    typeof artifact.content === "string"
      ? artifact.content
      : JSON.stringify(artifact.content, null, 2);
  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs">
        <span className="truncate font-mono text-slate-800">{artifact.name}</span>
        <Badge tone="info">{artifact.artifact_type}</Badge>
      </div>
      <pre className="max-h-60 overflow-auto rounded-md border border-slate-100 bg-slate-950 p-3 font-mono text-[11px] leading-5 text-slate-100">
        {content}
      </pre>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Runtime section — pending-approval banner + link group.
// Intentionally: no Approve/Reject/Modify controls, no Model Calls table,
// no Tool Runtime table. Users jump to /runs/:runId#<anchor> for details.
// ---------------------------------------------------------------------------

function RuntimeSection({
  activeRunId,
  pendingApprovalCount,
}: {
  activeRunId: string | null;
  pendingApprovalCount: number;
}): JSX.Element {
  const { text } = useI18n();

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <SectionHeader
        icon={<Shield className="h-4 w-4" />}
        title={text("运行时", "Runtime")}
        aside={activeRunId ? `run ${activeRunId.slice(0, 8)}` : text("未创建", "idle")}
      />
      <div className="space-y-3 p-3">
        {pendingApprovalCount > 0 && (
          <div
            role="alert"
            className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800"
          >
            {text(
              `有 ${pendingApprovalCount} 个待审批操作，请前往 Run 详情处理。`,
              `${pendingApprovalCount} approvals pending; please handle them in Run Detail.`,
            )}
          </div>
        )}

        {activeRunId === null ? (
          <EmptyState
            label={text(
              "Run 尚未创建，提交消息后可查看运行时。",
              "Run not created yet. Submit a message to populate runtime links.",
            )}
          />
        ) : (
          <LinkGroup runId={activeRunId} />
        )}
      </div>
    </section>
  );
}

type LinkItem = {
  to: string;
  label: string;
  hint: string;
};

function LinkGroup({ runId }: { runId: string }): JSX.Element {
  const { text } = useI18n();

  const items: LinkItem[] = [
    {
      to: `/runs/${runId}#approvals`,
      label: text("审批", "Approvals"),
      hint: text("在 Run 详情内处理审批", "Handle approvals inside Run Detail"),
    },
    {
      to: `/runs/${runId}#plan`,
      label: text("计划", "Plan"),
      hint: text("查看计划 DAG 视图", "Open the plan graph view"),
    },
    {
      to: `/runs/${runId}#model-calls`,
      label: text("模型调用", "Model Calls"),
      hint: text("完整模型调用表格", "Full model-call table"),
    },
    {
      to: `/runs/${runId}#tool-runtime`,
      label: text("工具运行时", "Tool Runtime"),
      hint: text("工具调用运行时表格", "Tool-call runtime table"),
    },
    {
      to: "/observability",
      label: text("可观测性", "Observability"),
      hint: text("跨 Run 的追踪与指标", "Cross-run traces and metrics"),
    },
    {
      to: "/evals",
      label: text("评测", "Evals"),
      hint: text("评测用例与评分", "Eval cases and scoring"),
    },
  ];

  return (
    <nav
      aria-label={text("运行时链接", "Runtime links")}
      className="flex flex-col gap-1.5"
    >
      {items.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className="group flex items-center justify-between gap-2 rounded-md border border-slate-200 bg-white px-3 py-2 text-xs text-slate-700 hover:border-slate-300 hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-slate-400"
        >
          <div className="min-w-0">
            <div className="font-medium text-slate-900">{item.label}</div>
            <div className="truncate text-[11px] text-slate-500">{item.hint}</div>
          </div>
          <ExternalLink
            aria-hidden="true"
            className="h-3.5 w-3.5 shrink-0 text-slate-400 group-hover:text-slate-600"
          />
        </Link>
      ))}
    </nav>
  );
}

// ---------------------------------------------------------------------------
// Internal UI bits.
// ---------------------------------------------------------------------------

function SectionHeader({
  icon,
  title,
  aside,
}: {
  icon: JSX.Element;
  title: string;
  aside?: string;
}): JSX.Element {
  return (
    <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-slate-950">
        {icon}
        {title}
      </div>
      {aside ? <span className="text-xs text-slate-500">{aside}</span> : null}
    </div>
  );
}

function EmptyState({ label }: { label: string }): JSX.Element {
  return (
    <div className="rounded-md border border-dashed border-slate-200 p-3 text-center text-xs text-slate-400">
      {label}
    </div>
  );
}
