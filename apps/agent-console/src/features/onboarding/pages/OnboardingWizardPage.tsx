import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, CheckCircle2, Gauge, KeyRound, Play, Settings2 } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input } from "../../../components/ui/input";
import {
  completeOnboarding,
  createAgentDefinition,
  getOnboardingState,
  loadDemoData,
  updateOnboardingState,
} from "../../tasks/api";

const providers = [
  { id: "deepseek", label: "DeepSeek", enabled: true },
  { id: "openai-compatible", label: "OpenAI GPT-5.5", enabled: true },
  { id: "anthropic", label: "Anthropic", enabled: false },
];

const templates = [
  { id: "research", name: "研究助手", prompt: "Answer with grounded evidence and cite run details." },
  { id: "code-review", name: "代码审查", prompt: "Review code for correctness, risks, and missing tests." },
  { id: "support", name: "客服回复", prompt: "Draft concise customer support responses with clear next steps." },
];

export function OnboardingWizardPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const requestedStep = Number(searchParams.get("step") ?? 0);
  const state = useQuery({ queryKey: ["onboarding", "state"], queryFn: getOnboardingState });
  const initialStep = requestedStep >= 1 && requestedStep <= 4 ? requestedStep : state.data?.current_step ?? 1;
  const [localStep, setLocalStep] = useState(initialStep);
  const step = state.data ? Math.max(localStep, state.data.current_step) : localStep;
  const [provider, setProvider] = useState("deepseek");
  const [endpoint, setEndpoint] = useState("https://api.deepseek.com");
  const [apiKey, setApiKey] = useState("");
  const [selectedTemplate, setSelectedTemplate] = useState("research");
  const [agentId, setAgentId] = useState("first-run-agent");
  const [demoTaskId, setDemoTaskId] = useState<string | null>(null);

  const saveProgress = useMutation({
    mutationFn: updateOnboardingState,
    onSuccess: async (next) => {
      setLocalStep(next.current_step);
      await queryClient.invalidateQueries({ queryKey: ["onboarding", "state"] });
    },
  });
  const createAgent = useMutation({
    mutationFn: () => {
      const template = templates.find((item) => item.id === selectedTemplate) ?? templates[0];
      return createAgentDefinition({
        id: agentId,
        name: template.name,
        description: "Created from first-run onboarding",
        role: "assistant",
        model_provider: "default",
        model_name: "default",
        system_prompt: template.prompt,
        tools_json: [],
        routing_tags: ["first-run"],
        max_parallel_assignments: 1,
        template_id: selectedTemplate,
      });
    },
    onSuccess: async (agent) => {
      notifyFeedback({ tone: "success", title: "首个智能体已创建", description: agent.name });
      await saveProgress.mutateAsync({ current_step: 4, agent_id: agent.id });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "智能体创建失败",
        description: feedbackErrorMessage(error, "请检查智能体 ID 是否重复。"),
      });
    },
  });
  const loadDemo = useMutation({
    mutationFn: loadDemoData,
    onSuccess: async (result) => {
      setDemoTaskId(result.task_id);
      notifyFeedback({ tone: "success", title: "演示任务已准备", description: result.task_id ?? undefined });
      await complete.mutateAsync({ demo_task_id: result.task_id ?? null, agent_id: agentId });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: "Demo 加载失败",
        description: feedbackErrorMessage(error, "请确认当前账号具备管理员权限。"),
      });
    },
  });
  const complete = useMutation({
    mutationFn: completeOnboarding,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["onboarding", "state"] });
      navigate("/");
    },
  });

  const providerSummary = useMemo(
    () => ({ provider, endpoint, key_configured: apiKey.trim().length > 0 }),
    [apiKey, endpoint, provider],
  );

  const moveTo = async (nextStep: number) => {
    setLocalStep(nextStep);
    await saveProgress.mutateAsync({ current_step: nextStep, provider_json: providerSummary });
  };

  return (
    <ConsoleShell title="首次设置">
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-panel">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="text-lg font-semibold text-slate-950">首次运行设置</h1>
              <p className="mt-1 text-sm text-slate-500">4 步完成模型、智能体和演示运行的最小闭环。</p>
            </div>
            <Button
              onClick={async () => {
                await saveProgress.mutateAsync({ current_step: step, skipped: true });
                navigate("/");
              }}
              disabled={saveProgress.isPending}
            >
              跳过
            </Button>
          </div>
          <div className="mt-4 grid grid-cols-4 gap-2">
            {[1, 2, 3, 4].map((item) => (
              <button
                key={item}
                type="button"
                data-testid={`step-indicator-${item}`}
                onClick={() => setLocalStep(item)}
                className={`h-2 rounded-full ${item <= step ? "bg-slate-900" : "bg-slate-200"}`}
                aria-label={`步骤 ${item}`}
              />
            ))}
          </div>
        </section>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              {step === 1 && <KeyRound className="h-4 w-4" />}
              {step === 2 && <Settings2 className="h-4 w-4" />}
              {step === 3 && <Bot className="h-4 w-4" />}
              {step === 4 && <Play className="h-4 w-4" />}
              Step {step}
            </div>
            <Badge tone={state.data?.completed ? "success" : "info"}>
              {state.data?.completed ? "已完成" : "进行中"}
            </Badge>
          </CardHeader>
          <div className="p-4">
            {step === 1 ? (
              <div className="space-y-4">
                <div className="text-sm font-semibold text-slate-900">选择 LLM Provider</div>
                <div className="grid gap-2 md:grid-cols-3">
                  {providers.map((item) => (
                    <button
                      key={item.id}
                      data-testid={`provider-${item.id}`}
                      disabled={!item.enabled}
                      onClick={() => setProvider(item.id)}
                      className={`rounded-lg border p-3 text-left text-sm transition ${
                        provider === item.id ? "border-slate-900 bg-slate-50" : "border-slate-200 bg-white"
                      } disabled:cursor-not-allowed disabled:opacity-50`}
                    >
                      <div className="font-semibold text-slate-900">{item.label}</div>
                      <div className="mt-1 text-xs text-slate-500">{item.enabled ? "可配置" : "占位待接入"}</div>
                    </button>
                  ))}
                </div>
                <Button data-testid="next-button" variant="primary" onClick={() => moveTo(2)}>下一步</Button>
              </div>
            ) : null}

            {step === 2 ? (
              <div className="grid gap-4">
                <div>
                  <div className="text-sm font-semibold text-slate-900">配置模型连接</div>
                  <p className="mt-1 text-xs text-slate-500">保存 provider 摘要；正式密钥仍应通过后端环境变量或模型设置管理。</p>
                </div>
                <label className="grid gap-1 text-xs font-medium text-slate-600">
                  Endpoint
                  <Input data-testid="endpoint-input" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} />
                </label>
                <label className="grid gap-1 text-xs font-medium text-slate-600">
                  API Key
                  <Input data-testid="api-key-input" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} />
                </label>
                <div className="flex gap-2">
                  <Link to="/settings/models"><Button>打开模型设置</Button></Link>
                  <Button data-testid="save-and-continue-button" variant="primary" onClick={() => moveTo(3)}>保存并继续</Button>
                </div>
              </div>
            ) : null}

            {step === 3 ? (
              <div className="grid gap-4">
                <div className="text-sm font-semibold text-slate-900">创建第一个智能体</div>
                <div className="grid gap-2 md:grid-cols-3">
                  {templates.map((template) => (
                    <button
                      key={template.id}
                      data-testid={`template-${template.id}`}
                      onClick={() => setSelectedTemplate(template.id)}
                      className={`rounded-lg border p-3 text-left text-sm ${
                        selectedTemplate === template.id ? "border-slate-900 bg-slate-50" : "border-slate-200"
                      }`}
                    >
                      <div className="font-semibold text-slate-900">{template.name}</div>
                      <div className="mt-1 text-xs text-slate-500">{template.prompt}</div>
                    </button>
                  ))}
                </div>
                <label className="grid gap-1 text-xs font-medium text-slate-600">
                  智能体 ID
                  <Input data-testid="agent-id-input" value={agentId} onChange={(event) => setAgentId(event.target.value)} />
                </label>
                <Button data-testid="create-agent-button" variant="primary" onClick={() => createAgent.mutate()} disabled={createAgent.isPending || !agentId.trim()}>
                  <Bot className="h-3.5 w-3.5" />
                  从模板创建
                </Button>
              </div>
            ) : null}

            {step === 4 ? (
              <div className="grid gap-4">
                <div>
                  <div className="text-sm font-semibold text-slate-900">运行演示任务</div>
                  <p className="mt-1 text-xs text-slate-500">加载演示数据后会生成历史运行，可直接跳到运行详情查看。</p>
                </div>
                {demoTaskId ? (
                  <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                    <CheckCircle2 className="mr-2 inline h-4 w-4" />
                    演示运行已创建：{demoTaskId}
                  </div>
                ) : null}
                <div className="flex flex-wrap gap-2">
                  <Button data-testid="trigger-demo-button" variant="primary" onClick={() => loadDemo.mutate()} disabled={loadDemo.isPending}>
                    <Gauge className="h-3.5 w-3.5" />
                    触发演示
                  </Button>
                  <Button data-testid="complete-setup-button" onClick={() => complete.mutate({ agent_id: agentId, demo_task_id: demoTaskId })} disabled={complete.isPending}>
                    完成设置
                  </Button>
                  {demoTaskId ? <Link to={`/runs/${demoTaskId}`}><Button>打开运行详情</Button></Link> : null}
                </div>
              </div>
            ) : null}
          </div>
        </Card>
      </div>
    </ConsoleShell>
  );
}
