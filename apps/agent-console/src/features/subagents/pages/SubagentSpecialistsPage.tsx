import { type FormEvent, type ReactNode, useMemo, useState } from "react";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, BrainCircuit, FilePlus2, ListFilter, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge, statusTone } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input, Textarea } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import {
  archiveSubagentSpecialist,
  createSubagentSpecialist,
  getSubagentSpecialistStats,
  listSubagentSpecialists,
  type SubagentSpecialist,
  type SubagentSpecialistCreatePayload,
  type SubagentSpecialistStats,
} from "../../tasks/api";

const DEFAULT_SCHEMA = `{
  "type": "object",
  "required": ["summary"],
  "properties": {
    "summary": { "type": "string" }
  }
}`;

const DEFAULT_BUDGET = `{
  "max_runtime_seconds": 900,
  "max_tokens": 8000,
  "max_tool_calls": 8,
  "max_cost_usd": 2
}`;

type VisibilityFilter = "active" | "system" | "org" | "archived";

type SpecialistFormState = {
  slug: string;
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

const initialForm: SpecialistFormState = {
  slug: "",
  displayName: "",
  description: "",
  role: "specialist",
  systemPrompt: "",
  capabilitySlugs: "",
  triggerKeywords: "",
  outputSchema: DEFAULT_SCHEMA,
  budget: DEFAULT_BUDGET,
  visibility: "org",
};

export function SubagentSpecialistsPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<VisibilityFilter>("active");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState<SpecialistFormState>(initialForm);
  const [formError, setFormError] = useState<string | null>(null);
  const specialistsQuery = useQuery({
    queryKey: ["subagent-specialists", "all"],
    queryFn: () => listSubagentSpecialists({ include_archived: true }),
  });
  const specialists = specialistsQuery.data?.items ?? [];
  const filtered = useMemo(
    () =>
      specialists.filter((specialist) => {
        if (filter === "active") return specialist.status === "ACTIVE";
        if (filter === "system") return specialist.visibility === "system";
        if (filter === "org") return specialist.visibility !== "system";
        return specialist.status === "ARCHIVED";
      }),
    [filter, specialists],
  );
  const statsQueries = useQueries({
    queries: filtered.map((specialist) => ({
      queryKey: ["subagent-specialist-stats", specialist.id, "30d"],
      queryFn: () => getSubagentSpecialistStats(specialist.id, "30d"),
      enabled: specialist.status === "ACTIVE",
    })),
  });
  const statsBySpecialistId = useMemo(() => {
    const entries = filtered.map((specialist, index) => [
      specialist.id,
      statsQueries[index]?.data,
    ]);
    return new Map(entries as Array<[string, SubagentSpecialistStats | undefined]>);
  }, [filtered, statsQueries]);
  const counts = useMemo(() => specialistCounts(specialists), [specialists]);
  const createMutation = useMutation({
    mutationFn: (payload: SubagentSpecialistCreatePayload) => createSubagentSpecialist(payload),
    onSuccess: async (specialist) => {
      setDialogOpen(false);
      setForm(initialForm);
      setFormError(null);
      notifyFeedback({
        tone: "success",
        title: text("专家模板已创建", "Specialist created"),
        description: `${specialist.display_name} / ${specialist.slug}`,
      });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialists"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("专家模板创建失败", "Specialist creation failed"),
        description: feedbackErrorMessage(error, text("请检查 slug、Schema 和预算格式。", "Check the slug, schema, and budget format.")),
      });
    },
  });
  const archiveMutation = useMutation({
    mutationFn: (specialistId: string) => archiveSubagentSpecialist(specialistId),
    onSuccess: async () => {
      notifyFeedback({
        tone: "warning",
        title: text("专家模板已归档", "Specialist archived"),
        description: text("归档模板不会参与后续自动匹配。", "Archived templates will not be used for future automatic matching."),
      });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialists"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("专家模板归档失败", "Specialist archive failed"),
        description: feedbackErrorMessage(error, text("system 模板不可归档。", "System templates cannot be archived.")),
      });
    },
  });

  const submitCreate = (event: FormEvent) => {
    event.preventDefault();
    const parsed = parseSpecialistForm(form);
    if ("error" in parsed) {
      setFormError(parsed.error);
      return;
    }
    setFormError(null);
    createMutation.mutate(parsed.payload);
  };

  return (
    <ConsoleShell title={text("专家库", "Specialist Library")}>
      <div className="mx-auto max-w-[1440px] space-y-4 p-6">
        <section className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-2 text-lg font-semibold tracking-tight text-slate-900">
              <BrainCircuit className="h-4 w-4" /> {text("子代理专家库", "Subagent Specialist Library")}
            </div>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">
              {text(
                "把角色提示词、工具白名单、结构化输出 Schema 和预算打包成可审计的子代理模板。",
                "Package role prompts, tool whitelists, structured output schemas, and budgets into auditable subagent templates.",
              )}
            </p>
          </div>
          <Button type="button" variant="primary" onClick={() => setDialogOpen(true)}>
            <FilePlus2 className="h-3.5 w-3.5" /> {text("创建专家", "Create Specialist")}
          </Button>
        </section>

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label={text("活跃模板", "Active")} value={counts.active} />
          <Metric label="System" value={counts.system} />
          <Metric label={text("组织模板", "Org")} value={counts.org} />
          <Metric label={text("已归档", "Archived")} value={counts.archived} />
        </section>

        <Card>
          <div className="flex flex-wrap items-center gap-2 p-3">
            <div className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700">
              <ListFilter className="h-3.5 w-3.5" /> {text("筛选", "Filter")}
            </div>
            {[
              ["active", text("活跃", "Active"), counts.active],
              ["system", "System", counts.system],
              ["org", text("组织", "Org"), counts.org],
              ["archived", text("已归档", "Archived"), counts.archived],
            ].map(([value, label, count]) => (
              <button
                key={String(value)}
                type="button"
                aria-pressed={filter === value}
                onClick={() => setFilter(value as VisibilityFilter)}
                className={
                  filter === value
                    ? "rounded-md border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs text-slate-900"
                    : "rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
                }
              >
                {label}
                <span className="ml-1 font-mono text-[10px] text-slate-400">{count}</span>
              </button>
            ))}
          </div>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <ShieldCheck className="h-4 w-4" />
              {text("专家模板", "Specialist Templates")}
            </div>
            <span className="text-xs text-slate-500">
              {specialistsQuery.isLoading
                ? text("加载中...", "Loading...")
                : text(`${filtered.length} 个模板`, `${filtered.length} templates`)}
            </span>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("专家", "Specialist")}</Th>
                <Th>{text("角色", "Role")}</Th>
                <Th>{text("30 天成功率 / 调用", "30d Success / Invocations")}</Th>
                <Th>{text("可见性", "Visibility")}</Th>
                <Th>{text("状态", "Status")}</Th>
                <Th>{text("工具白名单", "Tool Whitelist")}</Th>
                <Th>{text("预算", "Budget")}</Th>
                <Th>{text("更新", "Updated")}</Th>
                <Th>{text("操作", "Actions")}</Th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((specialist) => {
                const stats = statsBySpecialistId.get(specialist.id);
                return (
                  <tr key={specialist.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                    <Td>
                      <Link
                        to={`/subagent-specialists/${specialist.id}`}
                        className="font-semibold text-slate-900 hover:text-slate-950"
                      >
                        {specialist.display_name}
                      </Link>
                      <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500">
                        <span className="font-mono">{specialist.slug}</span>
                        <span className="max-w-[280px] truncate">{specialist.description}</span>
                      </div>
                    </Td>
                    <Td className="font-mono text-slate-600">{specialist.role}</Td>
                    <Td className="font-mono text-[11px] text-slate-700">
                      {stats ? (
                        <>
                          <span>{formatRate(stats.success_rate)}</span>
                          <span aria-hidden="true"> / </span>
                          <span>{stats.total_invocations.toLocaleString()}</span>
                          <span aria-hidden="true">次</span>
                        </>
                      ) : (
                        "- / -"
                      )}
                    </Td>
                    <Td>
                      <Badge tone={specialist.visibility === "system" ? "purple" : "info"}>
                        {specialist.visibility}
                      </Badge>
                    </Td>
                    <Td>
                      <Badge tone={statusTone(specialist.status)}>{statusLabel(specialist.status)}</Badge>
                    </Td>
                    <Td className="font-mono text-[11px] text-slate-500">
                      {specialist.capability_slugs_json.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {specialist.capability_slugs_json.slice(0, 3).map((capability) => (
                            <Badge key={capability} tone="neutral" className="font-mono text-[10px]">
                              {capability}
                            </Badge>
                          ))}
                          {specialist.capability_slugs_json.length > 3 ? (
                            <Badge tone="info" className="font-mono text-[10px]">
                              +{specialist.capability_slugs_json.length - 3}
                            </Badge>
                          ) : null}
                        </div>
                      ) : (
                        text("未限制", "Unrestricted")
                      )}
                    </Td>
                    <Td className="font-mono text-[11px] text-slate-500">
                      {budgetSummary(specialist.budget_json)}
                    </Td>
                    <Td className="font-mono text-slate-500">{formatShortDate(specialist.updated_at)}</Td>
                    <Td>
                      <Button
                        type="button"
                        variant="ghost"
                        disabled={specialist.visibility === "system" || specialist.status === "ARCHIVED" || archiveMutation.isPending}
                        onClick={() => archiveMutation.mutate(specialist.id)}
                      >
                        <Archive className="h-3.5 w-3.5" /> {text("归档", "Archive")}
                      </Button>
                    </Td>
                  </tr>
                );
              })}
              {filtered.length === 0 && (
                <tr>
                  <Td colSpan={9} className="py-8 text-center text-slate-500">
                    {text("当前筛选下没有专家模板。", "No specialist templates match this filter.")}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>

        <ConfigDialog
          open={dialogOpen}
          title={text("创建子代理专家", "Create Subagent Specialist")}
          description={text(
            "组织模板创建后可被计划步骤按关键词匹配，也可以在恢复/测试路径手动指定。",
            "Organization templates can be matched by plan-step keywords or manually selected in recovery and test paths.",
          )}
          onClose={() => setDialogOpen(false)}
          className="max-w-4xl"
        >
          <form className="space-y-4" onSubmit={submitCreate}>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <Field label="Slug">
                <Input
                  required
                  value={form.slug}
                  onChange={(event) => setForm({ ...form, slug: event.target.value })}
                  placeholder="security-reviewer"
                />
              </Field>
              <Field label={text("名称", "Name")}>
                <Input
                  required
                  value={form.displayName}
                  onChange={(event) => setForm({ ...form, displayName: event.target.value })}
                  placeholder="安全审查专家"
                />
              </Field>
              <Field label={text("角色", "Role")}>
                <Input
                  required
                  value={form.role}
                  onChange={(event) => setForm({ ...form, role: event.target.value })}
                  placeholder="reviewer"
                />
              </Field>
            </div>
            <Field label={text("说明", "Description")}>
              <Input
                required
                value={form.description}
                onChange={(event) => setForm({ ...form, description: event.target.value })}
                placeholder="审查变更中的安全风险和证据缺口"
              />
            </Field>
            <Field label={text("系统提示词", "System Prompt")}>
              <Textarea
                required
                value={form.systemPrompt}
                onChange={(event) => setForm({ ...form, systemPrompt: event.target.value })}
                className="min-h-24 font-mono text-xs"
              />
            </Field>
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <Field label={text("能力白名单", "Capability Whitelist")}>
                <Input
                  value={form.capabilitySlugs}
                  onChange={(event) => setForm({ ...form, capabilitySlugs: event.target.value })}
                  placeholder="mcp_context_search, shell_read"
                />
              </Field>
              <Field label={text("触发关键词", "Trigger Keywords")}>
                <Input
                  value={form.triggerKeywords}
                  onChange={(event) => setForm({ ...form, triggerKeywords: event.target.value })}
                  placeholder="安全, review, risk"
                />
              </Field>
              <Field label={text("可见性", "Visibility")}>
                <select
                  className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm"
                  value={form.visibility}
                  onChange={(event) =>
                    setForm({ ...form, visibility: event.target.value as "org" | "private" })
                  }
                >
                  <option value="org">org</option>
                  <option value="private">private</option>
                </select>
              </Field>
            </div>
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
              <Field label="Output JSON Schema">
                <Textarea
                  required
                  value={form.outputSchema}
                  onChange={(event) => setForm({ ...form, outputSchema: event.target.value })}
                  className="min-h-52 font-mono text-xs"
                />
              </Field>
              <Field label={text("预算 JSON", "Budget JSON")}>
                <Textarea
                  required
                  value={form.budget}
                  onChange={(event) => setForm({ ...form, budget: event.target.value })}
                  className="min-h-52 font-mono text-xs"
                />
              </Field>
            </div>
            {formError ? (
              <div className="rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700">
                {formError}
              </div>
            ) : null}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={() => setDialogOpen(false)}>
                {text("取消", "Cancel")}
              </Button>
              <Button type="submit" variant="primary" disabled={createMutation.isPending}>
                {createMutation.isPending ? text("创建中", "Creating") : text("创建专家", "Create Specialist")}
              </Button>
            </div>
          </form>
        </ConfigDialog>
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

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <div className="p-3">
        <div className="text-xs text-slate-500">{label}</div>
        <div className="mt-1 text-2xl font-semibold text-slate-950">{value}</div>
      </div>
    </Card>
  );
}

function specialistCounts(specialists: SubagentSpecialist[]) {
  return specialists.reduce(
    (counts, specialist) => {
      if (specialist.status === "ACTIVE") counts.active += 1;
      if (specialist.visibility === "system") counts.system += 1;
      if (specialist.visibility !== "system") counts.org += 1;
      if (specialist.status === "ARCHIVED") counts.archived += 1;
      return counts;
    },
    { active: 0, system: 0, org: 0, archived: 0 },
  );
}

function parseSpecialistForm(form: SpecialistFormState):
  | { payload: SubagentSpecialistCreatePayload }
  | { error: string } {
  let outputSchema: Record<string, unknown>;
  let budget: Record<string, unknown>;
  try {
    outputSchema = JSON.parse(form.outputSchema) as Record<string, unknown>;
  } catch (error) {
    return { error: `Output JSON Schema 不是合法 JSON：${error instanceof Error ? error.message : String(error)}` };
  }
  try {
    budget = JSON.parse(form.budget) as Record<string, unknown>;
  } catch (error) {
    return { error: `预算 JSON 不是合法 JSON：${error instanceof Error ? error.message : String(error)}` };
  }
  return {
    payload: {
      slug: form.slug.trim(),
      display_name: form.displayName.trim(),
      description: form.description.trim(),
      role: form.role.trim(),
      system_prompt: form.systemPrompt,
      capability_slugs_json: splitList(form.capabilitySlugs),
      output_schema_json: outputSchema,
      budget_json: budget,
      trigger_keywords_json: splitList(form.triggerKeywords),
      visibility: form.visibility,
    },
  };
}

function splitList(value: string) {
  return value
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function budgetSummary(budget: Record<string, unknown>) {
  const runtime = budget.max_runtime_seconds;
  const tokens = budget.max_tokens;
  const tools = budget.max_tool_calls;
  const cost = budget.max_cost_usd;
  return [
    typeof runtime === "number" ? `${runtime}s` : null,
    typeof tokens === "number" ? `${tokens} tok` : null,
    typeof tools === "number" ? `${tools} tools` : null,
    typeof cost === "number" ? `$${cost}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

function formatRate(value: number | null | undefined) {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "-";
}
