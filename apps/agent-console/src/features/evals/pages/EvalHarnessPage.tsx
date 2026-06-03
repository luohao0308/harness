import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { FlaskConical, GitCompare, Plus, Save, ShieldCheck, UserCheck } from "lucide-react";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { TermHint } from "../../../components/ui/term";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import {
  createEvalCaseFromRun,
  createEvalDataset,
  createEvalRun,
  getEvalRunRegression,
  listEvalCases,
  listEvalDatasets,
  listEvalRuns,
  setEvalBaseline,
  type RegressionDelta,
} from "../../tasks/api";
import { EvalCaseList } from "../components/EvalCaseList";
import { EvalRunResults } from "../components/EvalRunResults";

export function EvalHarnessPage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null);
  const [datasetName, setDatasetName] = useState("回归数据集");
  const [datasetDescription, setDatasetDescription] = useState("保存的智能体运行轨迹");
  const [sourceRunId, setSourceRunId] = useState(searchParams.get("run") ?? "");
  const [expectedStatus, setExpectedStatus] = useState("COMPLETED");
  const [agentId, setAgentId] = useState("default");

  const datasetsQuery = useQuery({ queryKey: ["eval-datasets"], queryFn: listEvalDatasets });
  const datasets = datasetsQuery.data?.items ?? [];
  const activeDatasetId = selectedDatasetId ?? datasets[0]?.id ?? null;
  const activeDataset = datasets.find((d) => d.id === activeDatasetId) ?? null;
  const casesQuery = useQuery({
    queryKey: ["eval-cases", activeDatasetId],
    queryFn: () => listEvalCases(activeDatasetId ?? ""),
    enabled: Boolean(activeDatasetId),
  });
  const runsQuery = useQuery({ queryKey: ["eval-runs"], queryFn: listEvalRuns });
  const latestRun = runsQuery.data?.items[0] ?? null;

  const regressionQuery = useQuery({
    queryKey: ["eval-regression", latestRun?.id],
    queryFn: () => getEvalRunRegression(latestRun!.id),
    enabled: Boolean(latestRun?.id),
  });
  const regressionDelta: RegressionDelta | null = regressionQuery.data ?? null;

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
      queryClient.invalidateQueries({ queryKey: ["eval-regression"] });
    },
  });
  const setBaselineMutation = useMutation({
    mutationFn: (evalRunId: string) => setEvalBaseline(activeDatasetId ?? "", evalRunId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["eval-datasets"] });
      queryClient.invalidateQueries({ queryKey: ["eval-regression"] });
    },
  });

  const canSaveCase = Boolean(activeDatasetId && sourceRunId.trim());
  const canRunEval = Boolean(activeDatasetId && (casesQuery.data?.items.length ?? 0) > 0);

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
    <ConsoleShell title={text("评测中心", "Eval Harness")}>
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
                {text("创建数据集", "Create Dataset")}
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
                    <span className="font-mono text-[10px]">{dataset.case_count} 个用例</span>
                  </div>
                  <div className="mt-1 flex items-center gap-1.5">
                    {dataset.baseline_run_id && (
                      <Badge tone="success">基线</Badge>
                    )}
                    <span className="truncate text-[11px] text-slate-500">
                      {dataset.description || dataset.id}
                    </span>
                  </div>
                </button>
              ))}
              {!datasetsQuery.isLoading && datasets.length === 0 && (
                <div className="px-2 py-8 text-center text-xs text-slate-500">
                  {text("还没有数据集", "No datasets yet")}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">
                {text("从运行保存用例", "Save Case From Run")}
              </div>
            </CardHeader>
            <form className="space-y-3 p-3" onSubmit={handleSaveCase}>
              <Input
                value={sourceRunId}
                onChange={(event) => setSourceRunId(event.target.value)}
                placeholder={text("运行 ID", "Run ID")}
              />
              <Input
                value={expectedStatus}
                onChange={(event) => setExpectedStatus(event.target.value)}
                placeholder="COMPLETED"
              />
              <Button type="submit" disabled={!canSaveCase} className="w-full gap-1.5">
                <Save className="h-3.5 w-3.5" />
                {text("保存为评测用例", "Save Eval Case")}
              </Button>
            </form>
          </Card>
        </section>

        <section className="space-y-4">
          <EvalCaseList
            cases={casesQuery.data?.items ?? []}
            isLoading={casesQuery.isLoading}
            agentId={agentId}
            onAgentIdChange={setAgentId}
            canRunEval={canRunEval}
            onRunEval={() => runEvalMutation.mutate()}
          />

          <EvalRunResults
            latestRun={latestRun}
            regressionDelta={regressionDelta}
            activeDatasetId={activeDatasetId}
            hasBaseline={Boolean(activeDataset?.baseline_run_id)}
            onSetBaseline={(evalRunId) => setBaselineMutation.mutate(evalRunId)}
          />
        </section>

        <aside className="space-y-4">
          <Card>
            <CardHeader>
              <div className="text-sm font-semibold text-slate-900">
                {text("回归门禁", "Regression Gate")}
              </div>
              <Badge tone={latestRun?.status === "COMPLETED" ? "success" : "neutral"}>
                {latestRun?.status === "COMPLETED" ? "接口已接入" : "等待中"}
              </Badge>
            </CardHeader>
            <div className="space-y-2 p-3 text-xs">
              <EvalReadiness
                icon={<ShieldCheck className="h-3.5 w-3.5" />}
                label={text("轨迹评分器", "Trace Grader")}
                status={latestRun ? "已启用" : "等待中"}
              />
              <EvalReadiness
                icon={<GitCompare className="h-3.5 w-3.5" />}
                label={<TermHint description="双版本对比评测">A/B</TermHint>}
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
                    <span>用例: {run.metrics_json.case_total ?? 0}</span>
                    <span>通过: {run.metrics_json.passed_total ?? 0}</span>
                    <span>智能体: {run.agent_id ?? "default"}</span>
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
  label: React.ReactNode;
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
