import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Play } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input, Textarea } from "../../../components/ui/input";
import { useI18n } from "../../../lib/i18n";
import { createTask, startTask, type TaskCreatePayload } from "../api";

export function TaskCreatePage() {
  const { text } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [payload, setPayload] = useState<TaskCreatePayload>({
    title: "分析代码仓库",
    goal: "分析当前 Python 项目并生成发现清单",
    model_provider: "openai-compatible",
    model_name: "default",
    max_runtime_seconds: 1800,
    max_subagents: 5,
    enable_sandbox: true,
    enable_network: false,
  });

  const createDraftMutation = useMutation({
    mutationFn: createTask,
    onSuccess: async (task) => {
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      navigate(`/tasks/${task.id}`);
    },
  });
  const runAgentMutation = useMutation({
    mutationFn: async (nextPayload: TaskCreatePayload) => {
      const task = await createTask(nextPayload);
      return startTask(task.id);
    },
    onSuccess: async (task) => {
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      await queryClient.invalidateQueries({ queryKey: ["observability", "summary"] });
      navigate(`/tasks/${task.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    runAgentMutation.mutate(payload);
  }

  const isSubmitting = createDraftMutation.isPending || runAgentMutation.isPending;

  return (
    <ConsoleShell title={text("任务 / 新建", "Tasks / New")}>
      <div className="mx-auto max-w-4xl p-6">
        <Card>
          <CardHeader>
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">{text("创建任务", "Create Task")}</div>
              <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
                {text("配置一次 Agent 执行", "Configure one Agent run")}
              </h1>
            </div>
          </CardHeader>
          <form onSubmit={submit} className="grid gap-5 p-5">
            <label className="grid gap-1.5 text-sm text-slate-700">
              {text("标题", "Title")}
              <Input
                value={payload.title}
                onChange={(event) => setPayload({ ...payload, title: event.target.value })}
              />
            </label>
            <label className="grid gap-1.5 text-sm text-slate-700">
              {text("目标", "Goal")}
              <Textarea
                value={payload.goal}
                onChange={(event) => setPayload({ ...payload, goal: event.target.value })}
              />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="grid gap-1.5 text-sm text-slate-700">
                {text("模型供应商", "Model provider")}
                <Input
                  value={payload.model_provider}
                  onChange={(event) =>
                    setPayload({ ...payload, model_provider: event.target.value })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm text-slate-700">
                {text("模型名称", "Model name")}
                <Input
                  value={payload.model_name}
                  onChange={(event) => setPayload({ ...payload, model_name: event.target.value })}
                />
              </label>
              <label className="grid gap-1.5 text-sm text-slate-700">
                {text("最大运行秒数", "Max runtime seconds")}
                <Input
                  type="number"
                  value={payload.max_runtime_seconds}
                  onChange={(event) =>
                    setPayload({ ...payload, max_runtime_seconds: Number(event.target.value) })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm text-slate-700">
                {text("最大子 Agent 数", "Max subagents")}
                <Input
                  type="number"
                  value={payload.max_subagents}
                  onChange={(event) =>
                    setPayload({ ...payload, max_subagents: Number(event.target.value) })
                  }
                />
              </label>
            </div>
            <div className="flex items-center gap-6 text-sm text-slate-700">
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={payload.enable_sandbox}
                  onChange={(event) =>
                    setPayload({ ...payload, enable_sandbox: event.target.checked })
                  }
                />
                {text("启用沙箱", "Enable sandbox")}
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={payload.enable_network}
                  onChange={(event) =>
                    setPayload({ ...payload, enable_network: event.target.checked })
                  }
                />
                {text("启用网络", "Enable network")}
              </label>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button type="button" onClick={() => navigate("/tasks")}>
                {text("取消", "Cancel")}
              </Button>
              <Button
                type="button"
                disabled={isSubmitting}
                onClick={() => createDraftMutation.mutate(payload)}
              >
                {createDraftMutation.isPending ? text("创建中...", "Creating...") : text("保存草稿", "Save Draft")}
              </Button>
              <Button type="submit" variant="primary" disabled={isSubmitting}>
                <Play className="h-3.5 w-3.5" />
                {runAgentMutation.isPending ? text("启动中...", "Starting...") : text("创建并启动 Agent", "Create & Run Agent")}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </ConsoleShell>
  );
}
