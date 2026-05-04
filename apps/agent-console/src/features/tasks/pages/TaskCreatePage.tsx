import { FormEvent, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { Input, Textarea } from "../../../components/ui/input";
import { createTask, type TaskCreatePayload } from "../api";

export function TaskCreatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [payload, setPayload] = useState<TaskCreatePayload>({
    title: "Analyze repository",
    goal: "Analyze this Python project and produce findings",
    model_provider: "openai-compatible",
    model_name: "default",
    max_runtime_seconds: 1800,
    max_subagents: 5,
    enable_sandbox: true,
    enable_network: false,
  });

  const createMutation = useMutation({
    mutationFn: createTask,
    onSuccess: async (task) => {
      await queryClient.invalidateQueries({ queryKey: ["tasks"] });
      navigate(`/tasks/${task.id}`);
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    createMutation.mutate(payload);
  }

  return (
    <ConsoleShell title="Tasks / New">
      <div className="mx-auto max-w-4xl p-6">
        <Card>
          <CardHeader>
            <div>
              <div className="text-[11px] tracking-widest text-slate-500">CREATE TASK</div>
              <h1 className="mt-1 text-xl font-semibold tracking-tight text-slate-900">
                Configure an agent run
              </h1>
            </div>
          </CardHeader>
          <form onSubmit={submit} className="grid gap-5 p-5">
            <label className="grid gap-1.5 text-sm text-slate-700">
              Title
              <Input
                value={payload.title}
                onChange={(event) => setPayload({ ...payload, title: event.target.value })}
              />
            </label>
            <label className="grid gap-1.5 text-sm text-slate-700">
              Goal
              <Textarea
                value={payload.goal}
                onChange={(event) => setPayload({ ...payload, goal: event.target.value })}
              />
            </label>
            <div className="grid grid-cols-2 gap-4">
              <label className="grid gap-1.5 text-sm text-slate-700">
                Model provider
                <Input
                  value={payload.model_provider}
                  onChange={(event) =>
                    setPayload({ ...payload, model_provider: event.target.value })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm text-slate-700">
                Model name
                <Input
                  value={payload.model_name}
                  onChange={(event) => setPayload({ ...payload, model_name: event.target.value })}
                />
              </label>
              <label className="grid gap-1.5 text-sm text-slate-700">
                Max runtime seconds
                <Input
                  type="number"
                  value={payload.max_runtime_seconds}
                  onChange={(event) =>
                    setPayload({ ...payload, max_runtime_seconds: Number(event.target.value) })
                  }
                />
              </label>
              <label className="grid gap-1.5 text-sm text-slate-700">
                Max subagents
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
                Enable sandbox
              </label>
              <label className="inline-flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={payload.enable_network}
                  onChange={(event) =>
                    setPayload({ ...payload, enable_network: event.target.checked })
                  }
                />
                Enable network
              </label>
            </div>
            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button type="button" onClick={() => navigate("/tasks")}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create task"}
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </ConsoleShell>
  );
}
