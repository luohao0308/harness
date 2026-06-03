import { type FormEvent, type ReactNode, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Archive,
  Beaker,
  BrainCircuit,
  ChevronRight,
  GitBranch,
  Save,
  ShieldCheck,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import {
  archiveSubagentSpecialist,
  getSubagentSpecialist,
  getSubagentSpecialistStats,
  listSubagents,
  preflightSubagentSpecialist,
  updateSubagentSpecialist,
  type SubagentListItem,
  type SubagentSpecialist,
  type SubagentSpecialistStats,
  type SubagentSpecialistUpdatePayload,
} from "../../tasks/api";

type StatsWindow = "7d" | "30d" | "all";

type SpecialistEditState = {
  displayName: string;
  description: string;
  role: string;
  systemPrompt: string;
  capabilitySlugs: string;
  triggerKeywords: string;
  outputSchema: string;
  budget: string;
  visibility: "org" | "private";
};

export function SubagentSpecialistDetailPage() {
  const { text } = useI18n();
  const { specialistId } = useParams();
  const queryClient = useQueryClient();
  const [editState, setEditState] = useState<SpecialistEditState | null>(null);
  const [editError, setEditError] = useState<string | null>(null);
  const [statsWindow, setStatsWindow] = useState<StatsWindow>("30d");
  const [sampleOutput, setSampleOutput] = useState(`{
  "summary": "样例输出"
}`);
  const specialistQuery = useQuery({
    queryKey: ["subagent-specialist", specialistId],
    queryFn: () => getSubagentSpecialist(specialistId!),
    enabled: Boolean(specialistId),
  });
  const specialist = specialistQuery.data;
  const historyQuery = useQuery({
    queryKey: ["subagents", "specialist-history", specialist?.id, specialist?.slug],
    queryFn: () => listSubagents({ limit: 500 }),
    enabled: Boolean(specialist),
  });
  const history = useMemo(
    () =>
      (historyQuery.data?.items ?? []).filter(
        (subagent) =>
          subagent.specialist_id === specialist?.id || subagent.specialist_slug === specialist?.slug,
      ),
    [historyQuery.data?.items, specialist?.id, specialist?.slug],
  );
  const statsQuery = useQuery({
    queryKey: ["subagent-specialist-stats", specialist?.id, statsWindow],
    queryFn: () => getSubagentSpecialistStats(specialist!.id, statsWindow),
    enabled: Boolean(specialist),
  });

  useEffect(() => {
    if (!specialist) return;
    setEditState(toEditState(specialist));
  }, [specialist]);

  const updateMutation = useMutation({
    mutationFn: (payload: SubagentSpecialistUpdatePayload) =>
      updateSubagentSpecialist(specialistId!, payload),
    onSuccess: async (updated) => {
      setEditError(null);
      notifyFeedback({
        tone: "success",
        title: text("专家模板已更新", "Specialist updated"),
        description: `${updated.display_name} / ${updated.slug}`,
      });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialist", specialistId] });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialists"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("专家模板更新失败", "Specialist update failed"),
        description: feedbackErrorMessage(error, text("请检查权限、Schema 和预算格式。", "Check permissions, schema, and budget format.")),
      });
    },
  });
  const archiveMutation = useMutation({
    mutationFn: () => archiveSubagentSpecialist(specialistId!),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: text("专家模板已归档", "Specialist archived"),
        description: text("归档模板不会参与后续自动匹配。", "Archived templates will not be used for future automatic matching."),
      });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialist", specialistId] });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialists"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("归档失败", "Archive failed"),
        description: feedbackErrorMessage(error, text("system 模板不可归档。", "System templates cannot be archived.")),
      });
    },
  });
  const preflightMutation = useMutation({
    mutationFn: (sample: Record<string, unknown>) => preflightSubagentSpecialist(specialistId!, sample),
    onSuccess: (result) => {
      notifyFeedback({
        tone: result.status === "passed" ? "success" : "warning",
        title: result.status === "passed" ? text("预检通过", "Preflight passed") : text("预检失败", "Preflight failed"),
        description:
          result.errors.length > 0
            ? result.errors.join("；")
            : `${text("Schema", "Schema")} ${result.output_schema_sha256.slice(0, 12)}`,
      });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("预检请求失败", "Preflight request failed"),
        description: feedbackErrorMessage(error, text("请检查样例 JSON。", "Check the sample JSON.")),
      });
    },
  });

  const submitUpdate = (event: FormEvent) => {
    event.preventDefault();
    if (!editState) return;
    const parsed = parseEditState(editState);
    if ("error" in parsed) {
      setEditError(parsed.error);
      return;
    }
    setEditError(null);
    updateMutation.mutate(parsed.payload);
  };

  const runPreflight = () => {
    let sample: Record<string, unknown>;
    try {
      sample = JSON.parse(sampleOutput) as Record<string, unknown>;
    } catch (error) {
      notifyFeedback({
        tone: "error",
        title: text("样例 JSON 无效", "Invalid sample JSON"),
        description: error instanceof Error ? error.message : String(error),
      });
      return;
    }
    preflightMutation.mutate(sample);
  };

  if (!specialist || !editState) {
    return (
      <ConsoleShell title={text("专家库 / 详情", "Specialists / Detail")}>
        <div className="p-6 text-sm text-slate-500">
          {specialistQuery.isError
            ? text("专家模板加载失败，请检查 ID 或权限。", "Failed to load specialist. Check the ID or permission.")
            : text("专家模板加载中...", "Loading specialist...")}
        </div>
      </ConsoleShell>
    );
  }

  const canEdit = specialist.visibility !== "system";

  return (
    <ConsoleShell title={`${text("专家库", "Specialists")} / ${specialist.slug}`}>
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <Link to="/subagent-specialists">{text("专家库", "Specialists")}</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono">{specialist.slug}</span>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="truncate text-xl font-semibold tracking-tight text-slate-900">
                {specialist.display_name}
              </h1>
              <Badge tone={statusTone(specialist.status)}>{statusLabel(specialist.status)}</Badge>
              <Badge tone={specialist.visibility === "system" ? "purple" : "info"}>
                {specialist.visibility}
              </Badge>
            </div>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">{specialist.description}</p>
            <div className="mt-2 flex flex-wrap items-center gap-5 text-xs text-slate-500">
              <span>
                Slug <span className="font-mono text-slate-800">{specialist.slug}</span>
              </span>
              <span>
                {text("角色", "Role")} <span className="font-mono text-slate-800">{specialist.role}</span>
              </span>
              <span>
                Schema <span className="font-mono text-slate-800">{specialist.output_schema_sha256.slice(0, 16)}</span>
              </span>
              <span>
                {text("更新", "Updated")}{" "}
                <span className="font-mono text-slate-800">{formatShortDate(specialist.updated_at)}</span>
              </span>
            </div>
          </div>
          <Button
            type="button"
            variant="danger"
            disabled={!canEdit || specialist.status === "ARCHIVED" || archiveMutation.isPending}
            onClick={() => archiveMutation.mutate()}
          >
            <Archive className="h-3.5 w-3.5" /> {text("归档", "Archive")}
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-12 space-y-4 xl:col-span-7">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <BrainCircuit className="h-4 w-4" />
                {text("专家契约", "Specialist Contract")}
              </div>
              {!canEdit ? (
                <Badge tone="purple">{text("System 模板只读", "System template is read-only")}</Badge>
              ) : null}
            </CardHeader>
            <form className="space-y-4 p-3" onSubmit={submitUpdate}>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <Field label={text("名称", "Name")}>
                  <Input
                    disabled={!canEdit}
                    value={editState.displayName}
                    onChange={(event) => setEditState({ ...editState, displayName: event.target.value })}
                  />
                </Field>
                <Field label={text("角色", "Role")}>
                  <Input
                    disabled={!canEdit}
                    value={editState.role}
                    onChange={(event) => setEditState({ ...editState, role: event.target.value })}
                  />
                </Field>
                <Field label={text("可见性", "Visibility")}>
                  <select
                    disabled={!canEdit}
                    className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm disabled:bg-slate-50"
                    value={editState.visibility}
                    onChange={(event) =>
                      setEditState({ ...editState, visibility: event.target.value as "org" | "private" })
                    }
                  >
                    <option value="org">org</option>
                    <option value="private">private</option>
                  </select>
                </Field>
              </div>
              <Field label={text("说明", "Description")}>
                <Input
                  disabled={!canEdit}
                  value={editState.description}
                  onChange={(event) => setEditState({ ...editState, description: event.target.value })}
                />
              </Field>
              <Field label={text("系统提示词", "System Prompt")}>
                <Textarea
                  disabled={!canEdit}
                  value={editState.systemPrompt}
                  onChange={(event) => setEditState({ ...editState, systemPrompt: event.target.value })}
                  className="min-h-32 font-mono text-xs disabled:bg-slate-50"
                />
              </Field>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <Field label={text("能力白名单", "Capability Whitelist")}>
                  <Input
                    disabled={!canEdit}
                    value={editState.capabilitySlugs}
                    onChange={(event) => setEditState({ ...editState, capabilitySlugs: event.target.value })}
                  />
                </Field>
                <Field label={text("触发关键词", "Trigger Keywords")}>
                  <Input
                    disabled={!canEdit}
                    value={editState.triggerKeywords}
                    onChange={(event) => setEditState({ ...editState, triggerKeywords: event.target.value })}
                  />
                </Field>
              </div>
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
                <Field label="Output JSON Schema">
                  <Textarea
                    disabled={!canEdit}
                    value={editState.outputSchema}
                    onChange={(event) => setEditState({ ...editState, outputSchema: event.target.value })}
                    className="min-h-72 font-mono text-xs disabled:bg-slate-50"
                  />
                </Field>
                <Field label={text("预算 JSON", "Budget JSON")}>
                  <Textarea
                    disabled={!canEdit}
                    value={editState.budget}
                    onChange={(event) => setEditState({ ...editState, budget: event.target.value })}
                    className="min-h-72 font-mono text-xs disabled:bg-slate-50"
                  />
                </Field>
              </div>
              {editError ? (
                <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
                  {editError}
                </div>
              ) : null}
              <div className="flex justify-end">
                <Button type="submit" variant="primary" disabled={!canEdit || updateMutation.isPending}>
                  <Save className="h-3.5 w-3.5" />
                  {updateMutation.isPending ? text("保存中", "Saving") : text("保存契约", "Save Contract")}
                </Button>
              </div>
            </form>
          </Card>
        </section>

        <aside className="col-span-12 space-y-4 xl:col-span-5">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Activity className="h-4 w-4" />
                {text("历史表现", "Historical Performance")}
              </div>
              <div className="flex rounded-md border border-slate-200 bg-white p-0.5">
                {(["7d", "30d", "all"] as StatsWindow[]).map((windowValue) => (
                  <button
                    key={windowValue}
                    type="button"
                    aria-pressed={statsWindow === windowValue}
                    onClick={() => setStatsWindow(windowValue)}
                    className={
                      statsWindow === windowValue
                        ? "rounded border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[10px] text-slate-900"
                        : "rounded px-2 py-0.5 font-mono text-[10px] text-slate-500 hover:bg-slate-50"
                    }
                  >
                    {windowValue}
                  </button>
                ))}
              </div>
            </CardHeader>
            <SpecialistStatsPanel
              stats={statsQuery.data}
              loading={statsQuery.isLoading}
            />
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Beaker className="h-4 w-4" />
                {text("输出预检", "Output Preflight")}
              </div>
              {preflightMutation.data ? (
                <Badge tone={preflightMutation.data.status === "passed" ? "success" : "warning"}>
                  {preflightMutation.data.status === "passed" ? text("通过", "Passed") : text("失败", "Failed")}
                </Badge>
              ) : null}
            </CardHeader>
            <div className="space-y-3 p-3">
              <Textarea
                aria-label={text("样例输出 JSON", "Sample output JSON")}
                value={sampleOutput}
                onChange={(event) => setSampleOutput(event.target.value)}
                className="min-h-36 font-mono text-xs"
              />
              <Button type="button" onClick={runPreflight} disabled={preflightMutation.isPending}>
                <Beaker className="h-3.5 w-3.5" />
                {preflightMutation.isPending ? text("预检中", "Preflighting") : text("运行预检", "Run Preflight")}
              </Button>
              {preflightMutation.data ? (
                <div className="rounded-md border border-slate-100 bg-slate-50 p-2 text-xs text-slate-600">
                  <div className="font-mono text-[11px] text-slate-500">
                    Schema {preflightMutation.data.output_schema_sha256}
                  </div>
                  {preflightMutation.data.errors.length > 0 ? (
                    <ul className="mt-2 list-disc space-y-1 pl-4 text-amber-700">
                      {preflightMutation.data.errors.map((error) => (
                        <li key={error}>{error}</li>
                      ))}
                    </ul>
                  ) : (
                    <div className="mt-2 text-emerald-700">
                      {text("样例输出满足当前 Schema。", "The sample output matches the current schema.")}
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <ShieldCheck className="h-4 w-4" />
                {text("预算与白名单", "Budget & Whitelist")}
              </div>
            </CardHeader>
            <div className="space-y-3 p-3 text-xs">
              <KeyValue label={text("预算", "Budget")} value={<JsonBlock value={specialist.budget_json} />} />
              <KeyValue
                label={text("能力白名单", "Capability Whitelist")}
                value={
                  specialist.capability_slugs_json.length > 0
                    ? specialist.capability_slugs_json.join(", ")
                    : text("未限制", "Unrestricted")
                }
              />
              <KeyValue
                label={text("触发关键词", "Trigger Keywords")}
                value={
                  specialist.trigger_keywords_json.length > 0
                    ? specialist.trigger_keywords_json.join(", ")
                    : text("无", "None")
                }
              />
            </div>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <GitBranch className="h-4 w-4" />
                {text("历史调用", "Invocation History")}
              </div>
              <span className="text-xs text-slate-500">{history.length}</span>
            </CardHeader>
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>{text("子代理", "Subagent")}</Th>
                  <Th>{text("状态", "Status")}</Th>
                  <Th>{text("输出", "Output")}</Th>
                  <Th>{text("完成", "Completed")}</Th>
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 12).map((subagent) => (
                  <tr key={subagent.id} className="border-t border-slate-100">
                    <Td>
                      <Link to={`/subagents/${subagent.id}`} className="font-mono text-slate-900">
                        {subagent.id.slice(0, 8)}
                      </Link>
                      <div className="mt-0.5 max-w-[180px] truncate text-[11px] text-slate-500">
                        {subagent.task_title}
                      </div>
                    </Td>
                    <Td>
                      <Badge tone={statusTone(subagent.status)}>{statusLabel(subagent.status)}</Badge>
                    </Td>
                    <Td className="max-w-[220px] truncate text-[11px] text-slate-500">
                      {subagent.output_summary ?? outputSummary(subagent)}
                    </Td>
                    <Td className="font-mono text-slate-500">
                      {subagent.completed_at ? formatShortDate(subagent.completed_at) : "-"}
                    </Td>
                  </tr>
                ))}
                {history.length === 0 && (
                  <tr>
                    <Td colSpan={4} className="py-8 text-center text-slate-500">
                      {text("暂无使用这个专家的子代理。", "No subagents have used this specialist yet.")}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>
        </aside>
      </div>
    </ConsoleShell>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-xs font-medium text-slate-700">
      <span>{label}</span>
      {children}
    </label>
  );
}

function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[11px] font-semibold text-slate-500">{label}</div>
      <div className="rounded-md border border-slate-100 bg-white p-2 text-slate-700">{value}</div>
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[320px] overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function SpecialistStatsPanel({
  stats,
  loading,
}: {
  stats: SubagentSpecialistStats | undefined;
  loading: boolean;
}) {
  if (loading && !stats) {
    return <div className="p-3 text-xs text-slate-500">历史表现加载中...</div>;
  }
  if (!stats) {
    return <div className="p-3 text-xs text-slate-500">暂无历史表现统计。</div>;
  }
  return (
    <div className="space-y-3 p-3 text-xs">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-2">
        <StatsMetric label="成功率" value={formatRate(stats.success_rate)} />
        <StatsMetric label="调用" value={stats.total_invocations.toLocaleString()} />
        <StatsMetric label="成功" value={stats.success_count.toLocaleString()} tone="success" />
        <StatsMetric label="失败" value={stats.failed_count.toLocaleString()} tone="failed" />
        <StatsMetric label="预算超限" value={stats.budget_exceeded_count.toLocaleString()} tone="warning" />
        <StatsMetric label="深度拒绝" value={stats.depth_rejected_count.toLocaleString()} tone="warning" />
        <StatsMetric label="平均耗时" value={formatMs(stats.avg_runtime_ms)} />
        <StatsMetric label="P95 耗时" value={formatMs(stats.p95_runtime_ms)} />
        <StatsMetric label="平均成本" value={`$${stats.avg_cost_usd}`} />
        <StatsMetric label="累计成本" value={`$${stats.total_cost_usd}`} />
        <StatsMetric label="平均工具" value={stats.avg_tool_calls.toFixed(1)} />
        <StatsMetric label="平均输出" value={`${stats.avg_output_size_bytes.toLocaleString()}B`} />
      </div>
      <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
        <div className="text-[11px] font-semibold text-slate-500">最近失败原因</div>
        {stats.recent_failure_reasons.length > 0 ? (
          <ul className="mt-2 space-y-1 font-mono text-[11px] text-slate-700">
            {stats.recent_failure_reasons.slice(0, 10).map((reason) => (
              <li key={reason.reason} className="flex items-center justify-between gap-3">
                <span className="truncate">{reason.reason}</span>
                <span className="text-slate-500">x {reason.count}</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-2 text-slate-400">无失败原因</div>
        )}
      </div>
    </div>
  );
}

function StatsMetric({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "failed" | "warning";
}) {
  const valueClass =
    tone === "success"
      ? "text-emerald-700"
      : tone === "failed"
        ? "text-red-700"
        : tone === "warning"
          ? "text-amber-700"
          : "text-slate-900";
  return (
    <div className="rounded-md border border-slate-100 bg-white p-2">
      <div className="text-[10px] text-slate-500">{label}</div>
      <div className={`mt-1 truncate font-mono text-sm ${valueClass}`}>{value}</div>
    </div>
  );
}

function formatRate(value: number | null | undefined) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "-";
}

function formatMs(value: number | null | undefined) {
  return typeof value === "number" ? `${value}ms` : "-";
}

function toEditState(specialist: SubagentSpecialist): SpecialistEditState {
  return {
    displayName: specialist.display_name,
    description: specialist.description,
    role: specialist.role,
    systemPrompt: specialist.system_prompt,
    capabilitySlugs: specialist.capability_slugs_json.join(", "),
    triggerKeywords: specialist.trigger_keywords_json.join(", "),
    outputSchema: JSON.stringify(specialist.output_schema_json, null, 2),
    budget: JSON.stringify(specialist.budget_json, null, 2),
    visibility: specialist.visibility === "private" ? "private" : "org",
  };
}

function parseEditState(state: SpecialistEditState):
  | { payload: SubagentSpecialistUpdatePayload }
  | { error: string } {
  let outputSchema: Record<string, unknown>;
  let budget: Record<string, unknown>;
  try {
    outputSchema = JSON.parse(state.outputSchema) as Record<string, unknown>;
  } catch (error) {
    return { error: `Output JSON Schema 不是合法 JSON：${error instanceof Error ? error.message : String(error)}` };
  }
  try {
    budget = JSON.parse(state.budget) as Record<string, unknown>;
  } catch (error) {
    return { error: `预算 JSON 不是合法 JSON：${error instanceof Error ? error.message : String(error)}` };
  }
  return {
    payload: {
      display_name: state.displayName.trim(),
      description: state.description.trim(),
      role: state.role.trim(),
      system_prompt: state.systemPrompt,
      capability_slugs_json: splitList(state.capabilitySlugs),
      output_schema_json: outputSchema,
      budget_json: budget,
      trigger_keywords_json: splitList(state.triggerKeywords),
      visibility: state.visibility,
    },
  };
}

function splitList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function outputSummary(subagent: SubagentListItem) {
  if (!subagent.output) return "-";
  const output = subagent.output.output_json;
  const summary = output.summary ?? output.answer;
  return typeof summary === "string" && summary.length > 0 ? summary : JSON.stringify(output).slice(0, 160);
}
