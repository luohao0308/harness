/**
 * InspectorDrawer — the on-demand side panel for Workspace.
 *
 * Satisfies:
 *   - Req 7.1–7.8 (scope invariant P4): the chat surface never renders the
 *     Plan DAG canvas, Model Calls table, Tool Call Runtime table, or
 *     Save/Run/Replay eval buttons. This drawer exposes compact pending tool
 *     approval controls plus links back to `/runs/:runId` anchors,
 *     `/observability`, `/evals`.
 *   - Req 9.3, 9.5: dialog role with aria-modal, aria-labelledby, Esc close,
 *     focus returns to the trigger button that opened the drawer.
 *   - Design §Inspector Drawer: artifacts and runtime sections render when
 *     `section` matches; runtime shows a
 *     pending-approval banner plus a LinkGroup.
 *
 * Intentionally: no Plan DAG canvas, no Model Calls or Tool Runtime tables, no "save as eval case" /
 * "Run Evals" / "Replay Run" buttons. All such destinations live in
 * `/runs/:runId` (see the LinkGroup inside the runtime section).
 */

import type { JSX } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Check, ExternalLink, FileCode2, Pencil, Shield, X } from "lucide-react";

import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { riskLabel, statusLabel } from "../../../lib/labels";
import { cn } from "../../../lib/utils";
import type { ConversationArtifact } from "../../../stores/workspaceStore";
import {
  approveToolApproval,
  modifyToolApproval,
  rejectToolApproval,
  type ToolApproval,
} from "../../tasks/api";
import { runDetailPath } from "../lib/runLinks";
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
  /** Pending and historical approvals from the active Run workspace projection. */
  approvals?: ToolApproval[];
  /** Parent is expected to have already capped this to the most recent 10. */
  artifacts: ConversationArtifact[];
  /** Callback to close the drawer (triggered by backdrop, close button, Esc). */
  onClose: () => void;
  runReturnTarget?: {
    agentId: string;
    conversationId?: string | null;
  };
  onApprovalsChanged?: () => Promise<unknown> | void;
};

type ModifyApprovalDialogState = {
  approval: ToolApproval;
  jsonText: string;
};

export function InspectorDrawer({
  section,
  activeRunId,
  pendingApprovalCount,
  approvals = [],
  artifacts,
  onClose,
  runReturnTarget,
  onApprovalsChanged,
}: InspectorDrawerProps): JSX.Element | null {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [modifyApprovalDialog, setModifyApprovalDialog] = useState<ModifyApprovalDialogState | null>(null);
  // Remember the element that had focus when the drawer opened so we can
  // restore it on close (Req 9.3). Falls back to document.body when the
  // trigger is no longer in the DOM.
  const lastTriggerRef = useRef<HTMLElement | null>(null);

  const refreshApprovals = useCallback(async () => {
    await Promise.resolve(onApprovalsChanged?.());
    if (activeRunId) {
      await queryClient.invalidateQueries({ queryKey: ["agent-run-workspace", activeRunId] });
    }
  }, [activeRunId, onApprovalsChanged, queryClient]);
  const approve = useMutation({
    mutationFn: (approvalId: string) => approveToolApproval(activeRunId!, approvalId, "Approved from Workspace inspector"),
    onSuccess: async () => {
      notifyFeedback({
        tone: "success",
        title: text("审批已通过", "Approval accepted"),
        description: text("工具审批状态已更新。", "The tool approval state has been updated."),
      });
      await refreshApprovals();
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("审批通过失败", "Approval failed"),
        description: feedbackErrorMessage(error, text("请刷新后重试审批操作。", "Refresh and retry the approval action.")),
      });
    },
  });
  const reject = useMutation({
    mutationFn: (approvalId: string) => rejectToolApproval(activeRunId!, approvalId, "Rejected from Workspace inspector"),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: text("审批已拒绝", "Approval rejected"),
        description: text("工具审批状态已更新为拒绝。", "The tool approval has been marked as rejected."),
      });
      await refreshApprovals();
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("审批拒绝失败", "Rejection failed"),
        description: feedbackErrorMessage(error, text("请刷新后重试拒绝操作。", "Refresh and retry the reject action.")),
      });
    },
  });
  const modify = useMutation({
    mutationFn: ({
      approvalId,
      modifiedInputJson,
    }: {
      approvalId: string;
      modifiedInputJson: Record<string, unknown>;
    }) =>
      modifyToolApproval(
        activeRunId!,
        approvalId,
        modifiedInputJson,
        "Modified and approved from Workspace inspector",
      ),
    onSuccess: async () => {
      setModifyApprovalDialog(null);
      notifyFeedback({
        tone: "success",
        title: text("审批已修改并批准", "Approval modified and accepted"),
        description: text("工具将使用修改后的 JSON 参数执行。", "The tool will run with the modified JSON payload."),
      });
      await refreshApprovals();
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("修改审批失败", "Modify approval failed"),
        description: feedbackErrorMessage(error, text("请检查 JSON 后重试。", "Check the JSON and retry.")),
      });
    },
  });

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
        className="fixed inset-y-14 right-0 z-50 w-[420px] overflow-y-auto border-l border-slate-200 bg-white shadow-none"
      >
        <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div>
            <div id="inspector-title" className="text-sm font-semibold text-slate-950">
              {title}
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {text(
                "按需展开的运行观察面板，详细操作请前往运行详情。",
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
              approvals={approvals}
              runReturnTarget={runReturnTarget}
              onApprove={(approvalId) => approve.mutate(approvalId)}
              onReject={(approvalId) => reject.mutate(approvalId)}
              onModify={(approval) =>
                setModifyApprovalDialog({
                  approval,
                  jsonText: JSON.stringify(approvalInputJson(approval), null, 2),
                })
              }
            />
          )}
        </div>
      </aside>
      <ModifyToolApprovalDialog
        state={modifyApprovalDialog}
        isSubmitting={modify.isPending}
        onChange={(jsonText) => {
          setModifyApprovalDialog((current) => (
            current ? { ...current, jsonText } : current
          ));
        }}
        onClose={() => {
          if (!modify.isPending) setModifyApprovalDialog(null);
        }}
        onSubmit={(approvalId, modifiedInputJson) => modify.mutate({ approvalId, modifiedInputJson })}
      />
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
// Runtime section — compact pending approvals + link group.
// Intentionally: no Model Calls table or Tool Runtime table. Users jump to
// /runs/:runId#<anchor> for full runtime evidence.
// ---------------------------------------------------------------------------

function RuntimeSection({
  activeRunId,
  pendingApprovalCount,
  approvals,
  runReturnTarget,
  onApprove,
  onReject,
  onModify,
}: {
  activeRunId: string | null;
  pendingApprovalCount: number;
  approvals: ToolApproval[];
  runReturnTarget?: {
    agentId: string;
    conversationId?: string | null;
  };
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
  onModify: (approval: ToolApproval) => void;
}): JSX.Element {
  const { text } = useI18n();
  const pendingApprovals = approvals.filter((approval) => approval.status === "PENDING");

  return (
    <section className="rounded-lg border border-slate-200 bg-white">
      <SectionHeader
        icon={<Shield className="h-4 w-4" />}
        title={text("运行时", "Runtime")}
        aside={activeRunId ? `运行 ${activeRunId.slice(0, 8)}` : text("未创建", "idle")}
      />
      <div className="space-y-3 p-3">
        {pendingApprovalCount > 0 && (
          <PendingApprovalsList
            approvals={pendingApprovals}
            pendingApprovalCount={pendingApprovalCount}
            onApprove={onApprove}
            onReject={onReject}
            onModify={onModify}
          />
        )}

        {activeRunId === null ? (
          <EmptyState
            label={text(
              "运行尚未创建，提交消息后可查看运行时。",
              "Run not created yet. Submit a message to populate runtime links.",
            )}
          />
        ) : (
          <LinkGroup runId={activeRunId} returnTarget={runReturnTarget} />
        )}
      </div>
    </section>
  );
}

function PendingApprovalsList({
  approvals,
  pendingApprovalCount,
  onApprove,
  onReject,
  onModify,
}: {
  approvals: ToolApproval[];
  pendingApprovalCount: number;
  onApprove: (approvalId: string) => void;
  onReject: (approvalId: string) => void;
  onModify: (approval: ToolApproval) => void;
}): JSX.Element {
  const { text } = useI18n();
  if (approvals.length === 0) {
    return (
      <div
        role="alert"
        className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800"
      >
        {text(
          `有 ${pendingApprovalCount} 个待审批操作，正在加载审批详情。`,
          `${pendingApprovalCount} approvals pending; approval details are loading.`,
        )}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div
        role="alert"
        className="rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-800"
      >
        {text(
          `有 ${pendingApprovalCount} 个待审批操作。`,
          `${pendingApprovalCount} approvals pending.`,
        )}
      </div>
      {approvals.map((approval) => (
        <div key={approval.id} className="rounded-md border border-slate-200 bg-white p-2 text-xs">
          <div className="flex items-center justify-between gap-2">
            <Badge tone={statusTone(approval.status)}>{statusLabel(approval.status)}</Badge>
            <span className="font-mono text-[11px] text-slate-500">{riskLabel(approval.risk_level)}</span>
          </div>
          <div className="mt-2 line-clamp-3 text-slate-600">{approval.reason}</div>
          <div className="mt-2 flex flex-wrap gap-1">
            <Button onClick={() => onApprove(approval.id)}>
              <Check className="h-3.5 w-3.5" />
              {text("批准", "Approve")}
            </Button>
            <Button variant="secondary" onClick={() => onModify(approval)}>
              <Pencil className="h-3.5 w-3.5" />
              {text("修改", "Modify")}
            </Button>
            <Button onClick={() => onReject(approval.id)}>
              <X className="h-3.5 w-3.5" />
              {text("拒绝", "Reject")}
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}

function ModifyToolApprovalDialog({
  state,
  isSubmitting,
  onChange,
  onClose,
  onSubmit,
}: {
  state: ModifyApprovalDialogState | null;
  isSubmitting: boolean;
  onChange: (jsonText: string) => void;
  onClose: () => void;
  onSubmit: (approvalId: string, modifiedInputJson: Record<string, unknown>) => void;
}): JSX.Element | null {
  const { text } = useI18n();
  const parsed = state ? parseApprovalJson(state.jsonText) : { value: null, error: null };
  const errorId = state ? `inspector-modify-approval-json-error-${state.approval.id}` : undefined;
  if (!state) return null;

  const submitDisabled = isSubmitting || parsed.value === null;

  return (
    <ConfigDialog
      open
      title={text("修改工具审批参数", "Modify tool approval payload")}
      description={text(
        "编辑 JSON 参数后将立即按修改后的内容批准此工具调用。",
        "Edit the JSON payload before approving this tool call with the modified input.",
      )}
      onClose={onClose}
      className="max-w-2xl"
    >
      <div className="space-y-4">
        <div className="rounded-md border border-slate-100 bg-slate-50 p-3 text-xs text-slate-600">
          <div className="font-mono text-slate-900">{state.approval.tool_call_id}</div>
          <div className="mt-1">{state.approval.reason}</div>
        </div>
        <label className="block text-xs font-medium text-slate-700" htmlFor="inspector-modify-approval-json">
          {text("JSON 参数", "JSON payload")}
        </label>
        <Textarea
          id="inspector-modify-approval-json"
          value={state.jsonText}
          onChange={(event) => onChange(event.target.value)}
          spellCheck={false}
          disabled={isSubmitting}
          aria-invalid={parsed.error ? true : undefined}
          aria-describedby={parsed.error ? errorId : undefined}
          className="min-h-72 font-mono text-xs leading-5"
        />
        {parsed.error ? (
          <div id={errorId} className="text-xs text-rose-600">
            {text(`JSON 无效：${parsed.error}`, `Invalid JSON: ${parsed.error}`)}
          </div>
        ) : null}
        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="ghost" onClick={onClose} disabled={isSubmitting}>
            {text("取消", "Cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => {
              if (parsed.value) onSubmit(state.approval.id, parsed.value);
            }}
            disabled={submitDisabled}
          >
            {isSubmitting ? text("提交中...", "Submitting...") : text("修改并批准", "Modify and approve")}
          </Button>
        </div>
      </div>
    </ConfigDialog>
  );
}

function approvalInputJson(approval: ToolApproval): Record<string, unknown> {
  const requestInput = approval.request_json.input_json;
  if (isJsonRecord(requestInput)) return requestInput;
  return {};
}

function parseApprovalJson(jsonText: string): {
  value: Record<string, unknown> | null;
  error: string | null;
} {
  if (jsonText.trim().length === 0) {
    return { value: null, error: "JSON payload is required" };
  }
  try {
    const value = JSON.parse(jsonText) as unknown;
    if (!isJsonRecord(value)) {
      return { value: null, error: "payload must be a JSON object" };
    }
    return { value, error: null };
  } catch (error) {
    return {
      value: null,
      error: error instanceof Error ? error.message : "parse failed",
    };
  }
}

function isJsonRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

type LinkItem = {
  to: string;
  label: string;
  hint: string;
};

function LinkGroup({
  runId,
  returnTarget,
}: {
  runId: string;
  returnTarget?: {
    agentId: string;
    conversationId?: string | null;
  };
}): JSX.Element {
  const { text } = useI18n();
  const runLink = (hash: string) => (
    returnTarget ? runDetailPath(runId, returnTarget, hash) : `/runs/${runId}#${hash}`
  );

  const items: LinkItem[] = [
    {
      to: runLink("approvals"),
      label: text("审批", "Approvals"),
      hint: text("在运行详情内处理审批", "Handle approvals inside Run Detail"),
    },
    {
      to: runLink("plan"),
      label: text("计划", "Plan"),
      hint: text("查看计划 DAG 视图", "Open the plan graph view"),
    },
    {
      to: runLink("model-calls"),
      label: text("模型调用", "Model Calls"),
      hint: text("完整模型调用表格", "Full model-call table"),
    },
    {
      to: runLink("tool-runtime"),
      label: text("工具运行时", "Tool Runtime"),
      hint: text("工具调用运行时表格", "Tool-call runtime table"),
    },
    {
      to: "/observability",
      label: text("可观测性", "Observability"),
      hint: text("跨运行的追踪与指标", "Cross-run traces and metrics"),
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
