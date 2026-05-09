import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, GitCompare, Play, Plus, Save, ShieldCheck, UserCheck } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import {
  createEvalCaseFromRun,
  createEvalDataset,
  createEvalRun,
  listEvalCases,
  listEvalDatasets,
  listEvalRuns,
} from "../../tasks/api";

const metricLabels: Record<string, string> = {
  task_success_rate: "Task Success",
  tool_selection_accuracy: "Tool Accuracy",
  policy_violation_rate: "Policy Violation",
  avg_latency_ms: "Avg Latency",
  avg_cost_usd: "Avg Cost",
  retry_rate: "Retry Rate",
  human_escalation_rate: "Human Escalation",
};

export function EvalHarnessPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [datasetName, setDatasetName] = useState("Regression Dataset");
  const [datasetDescription, setDatasetDescription] = useState("Saved Agent Run traces");
  const [sourceRunId, setSourceRunId] = useState("");
  const [expectedStatus, setExpectedStatus] = useState("COMPLETED");
  const [agentId, setAgentId] = useState("default");

  const datasetsQuery = useQuery({ queryKey: ["eval-datasets"], queryFn: listEvalDatasets });
  const datasets = datasetsQuery.data?.items ?? [];
  const activeDatasetId = selectedDatasetId ?? datasets[0]?.id ?? null;
  const casesQuery = useQuery({
    queryKey: ["eval-cases", activeDatasetId],
    queryFn: () => listEvalCases(activeDatasetId ?? ""),
    enabled: Boolean(activeDatasetId),
  });
  const runsQuery = useQuery({ queryKey: ["eval-runs"], queryFn: listEvalRuns });
  const latestRun = runsQuery.data?.items[0] ?? null;
  const metrics = latestRun?.metrics_json ?? {};

  const createDatasetMutation = useMutation({
    mutationFn: () => createEvalDataset({ name: datasetName, description: datasetDescription }),
    onSuccess: (dataset) => {
      setSelectedDatasetId(dataset.id);
      queryClient.invalidateQueries({ queryKey: ["eval-datasets"] });
    },
  });
  const saveCaseMutation = useMutation({
    mutationFn: () =>
      createEvalCaseFromRun(activeDatasetId ?? "", sourceRunId, {
        expected_json: { status: expectedStatus },
        tags_json: ["regression", "saved-run"],
      }),
    onSuccess: () => {
      setSourceRunId("");
      queryClient.invalidateQueries({ queryKey: ["eval-datasets"] });
      queryClient.invalidateQueries({ queryKey: ["eval-cases", activeDatasetId] });
    },
  });
  const runEvalMutation = useMutation({
    mutationFn: () => createEvalRun(activeDatasetId ?? "", { agent_id: agentId || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eval-runs"] });
    },
  });

  const canSaveCase = Boolean(activeDatasetId && sourceRunId.trim());
  const canRunEval = Boolean(activeDatasetId && (casesQuery.data?.items.length ?? 0) > 0);
  const metricEntries = useMemo(
    () => Object.entries(metrics).filter(([key]) => key in metricLabels),
    [metrics],
  );

  function handleCreateDataset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    createDatasetMutation.mutate();
  }

  function handleSaveCase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (canSaveCase) {
      saveCaseMutation.mutate();
    }
  }

  return (
    <ConsoleShell title={text("Eval Harness", "Eval Harness")}>
      <div className="mx-auto grid max-w-[1500px] grid-cols-[320px_minmax(0,1fr)_360px] gap-4 p-6">
        <section className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <FlaskConical className="h-4 w-4" />
                {text("数据集", "Datasets")}
              </div>
            </CardHeader>
            <form className="space-y-3 p-3" onSubmit={handleCreateDataset}>
              <Input value={datasetName} onChange={(event) => setDatasetName(event.target.value)} />
              <Input
                value={datasetDescription}
                onChange={(event) => setDatasetDescription(event.target.value)}
              />
              <Button type="submit" variant="primary" className="w-full gap-1.5">
                <Plus className="h-3.5 w-3.5" />
                {text("创建 Dataset", "Create Dataset")}
              </Button>
            </form>
            <div className="border-t border-slate-100 p-2">
              {datasets.map((dataset) => (
                <button
                  key={dataset.id}
                  className={`mb-1 w-full rounded-md px-2 py-2 text-left text-xs ${
                    activeDatasetId === dataset.id
                      ? "bg-slate-100 text-slate-900"
                      : "text-slate-600 hover:bg-slate-50"
                  }`}
                  onClick={() => setSelectedDatasetId(dataset.id)}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{dataset.name}</span>
                    <span className="font-mono text-[10px]">{dataset.case_count} cases</span>
                  </div>
                  <div className="mt-1 truncate text-[11px] text-slate-500">
                    {dataset.description || dataset.id}
                  </div>
                </button>
              ))}
              {!datasetsQuery.isLoading && datasets.length === 0 && (
                <div className="px-2 py-8 text-center text-xs text-slate-500">
                  {text("还没有 Dataset", "No datasets yet")}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">
                {text("从 Run 保存 Case", "Save Case From Run")}
              </div>
            </CardHeader>
            <form className="space-y-3 p-3" onSubmit={handleSaveCase}>
              <Input
                value={sourceRunId}
                onChange={(event) => setSourceRunId(event.target.value)}
                placeholder={text("Run ID", "Run ID")}
              />
              <Input
                value={expectedStatus}
                onChange={(event) => setExpectedStatus(event.target.value)}
                placeholder="COMPLETED"
              />
              <Button type="submit" disabled={!canSaveCase} className="w-full gap-1.5">
                <Save className="h-3.5 w-3.5" />
                {text("保存为 Eval Case", "Save Eval Case")}
              </Button>
            </form>
          </Card>
        </section>

        <section className="space-y-4">
          <Card className="overflow-hidden">
            <CardHeader>
              <div>
                <div className="text-sm font-semibold text-slate-900">
                  {text("Case 队列", "Case Queue")}
                </div>
                <div className="text-[11px] text-slate-500">
                  {text("每个 Case 都来自真实 Run 或显式输入", "Every case is backed by a run or explicit input")}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Input
                  value={agentId}
                  onChange={(event) => setAgentId(event.target.value)}
                  className="h-8 w-28"
                />
                <Button
                  variant="primary"
                  disabled={!canRunEval}
                  onClick={() => runEvalMutation.mutate()}
                  className="gap-1.5"
                >
                  <Play className="h-3.5 w-3.5" />
                  {text("运行评测", "Run Eval")}
                </Button>
              </div>
            </CardHeader>
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>Case</Th>
                  <Th>Source Run</Th>
                  <Th>Expected</Th>
                  <Th>Tags</Th>
                  <Th>Created</Th>
                </tr>
              </thead>
              <tbody>
                {(casesQuery.data?.items ?? []).map((item) => (
                  <tr key={item.id} className="border-t border-slate-100">
                    <Td className="font-mono text-slate-500">{item.id.slice(0, 8)}</Td>
                    <Td className="font-mono text-slate-600">
                      {item.source_task_id?.slice(0, 8) ?? "manual"}
                    </Td>
                    <Td className="font-mono text-slate-600">
                      {String(item.expected_json.status ?? "custom")}
                    </Td>
                    <Td>{item.tags_json.join(", ")}</Td>
                    <Td className="font-mono text-slate-500">{formatShortDate(item.created_at)}</Td>
                  </tr>
                ))}
                {!casesQuery.isLoading && (casesQuery.data?.items.length ?? 0) === 0 && (
                  <tr>
                    <Td colSpan={5} className="py-12 text-center text-slate-500">
                      {text("选择 Dataset 后保存 Run 作为评测用例", "Select a dataset and save a run as a case")}
                    </Td>
                  </tr>
                )}
              </tbody>
            </Table>
          </Card>

          <Card className="overflow-hidden">
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">
                {text("最近 Eval Run", "Latest Eval Run")}
              </div>
              {latestRun && <Badge>{latestRun.status}</Badge>}
            </CardHeader>
            <div className="grid grid-cols-4 gap-3 border-b border-slate-100 p-3">
              {metricEntries.map(([key, value]) => (
                <div key={key} className="rounded-md border border-slate-200 bg-slate-50 p-3">
                  <div className="text-[10px] uppercase text-slate-500">{metricLabels[key]}</div>
                  <div className="mt-1 font-mono text-lg text-slate-900">
                    {key.includes("latency") ? `${value}ms` : value}
                  </div>
                </div>
              ))}
              {!latestRun && (
                <div className="col-span-4 py-8 text-center text-xs text-slate-500">
                  {text("运行一次评测后这里会显示指标", "Metrics appear after an eval run")}
                </div>
              )}
            </div>
            <Table>
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>Result</Th>
                  <Th>Status</Th>
                  <Th>Task</Th>
                  <Th>Score</Th>
                  <Th>Trace Grader</Th>
                </tr>
              </thead>
              <tbody>
                {(latestRun?.results ?? []).map((result) => (
                  <tr key={result.id} className="border-t border-slate-100">
                    <Td className="font-mono text-slate-500">{result.id.slice(0, 8)}</Td>
                    <Td>
                      <Badge>{result.status}</Badge>
                    </Td>
                    <Td className="font-mono text-slate-600">
                      {result.task_id?.slice(0, 8) ?? "manual"}
                    </Td>
                    <Td className="font-mono text-slate-900">
                      {result.scores_json.task_success ?? 0}
                    </Td>
                    <Td className="text-slate-600">
                      {String(result.grader_trace_json.grader ?? "unknown")}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </Card>
        </section>

        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">
                {text("回归门禁", "Regression Gate")}
              </div>
              <Badge tone={latestRun?.status === "COMPLETED" ? "success" : "neutral"}>
                {latestRun?.status === "COMPLETED" ? "API-backed" : "waiting"}
              </Badge>
            </CardHeader>
            <div className="space-y-2 p-3 text-xs">
              <EvalReadiness
                icon={<ShieldCheck className="h-3.5 w-3.5" />}
                label={text("Trace Grader", "Trace Grader")}
                status={latestRun ? "active" : "waiting"}
              />
              <EvalReadiness
                icon={<GitCompare className="h-3.5 w-3.5" />}
                label="A/B"
                status={text("未启用", "Disabled")}
                disabled
              />
              <EvalReadiness
                icon={<UserCheck className="h-3.5 w-3.5" />}
                label={text("人工复核", "Human Review")}
                status={text("未启用", "Disabled")}
                disabled
              />
            </div>
          </Card>
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">
                {text("评测运行历史", "Eval Run History")}
              </div>
            </CardHeader>
            <div className="p-2">
              {(runsQuery.data?.items ?? []).map((run) => (
                <div key={run.id} className="mb-2 rounded-md border border-slate-200 p-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-slate-500">{run.id.slice(0, 8)}</span>
                    <Badge>{run.status}</Badge>
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-600">
                    <span>cases: {run.metrics_json.case_total ?? 0}</span>
                    <span>pass: {run.metrics_json.passed_total ?? 0}</span>
                    <span>agent: {run.agent_id ?? "default"}</span>
                    <span>{formatShortDate(run.created_at)}</span>
                  </div>
                </div>
              ))}
              {!runsQuery.isLoading && (runsQuery.data?.items.length ?? 0) === 0 && (
                <div className="px-2 py-8 text-center text-xs text-slate-500">
                  {text("暂无评测运行", "No eval runs yet")}
                </div>
              )}
            </div>
          </Card>
        </aside>
      </div>
    </ConsoleShell>
  );
}

function EvalReadiness({
  icon,
  label,
  status,
  disabled = false,
}: {
  icon: React.ReactNode;
  label: string;
  status: string;
  disabled?: boolean;
}) {
  return (
    <div className={disabled ? "flex items-center justify-between rounded-md border border-slate-100 p-2 opacity-60" : "flex items-center justify-between rounded-md border border-slate-100 p-2"}>
      <span className="inline-flex items-center gap-2 text-slate-700">
        {icon}
        {label}
      </span>
      <Badge tone={disabled ? "neutral" : "success"}>{status}</Badge>
    </div>
  );
}
