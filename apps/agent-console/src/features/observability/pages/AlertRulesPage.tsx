import { useState } from "react";
import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Pencil, Play, Plus, Send, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Input } from "../../../components/ui/input";
import { Table, Td, Th } from "../../../components/ui/table";
import { formatShortDate } from "../../../lib/utils";
import { NotificationChannelForm } from "../components/NotificationChannelForm";
import {
  createNotificationChannel,
  createAlertRule,
  deleteAlertRule,
  deleteNotificationChannel,
  evaluateAlertRules,
  listAlertEvents,
  listAlertRules,
  listNotificationChannels,
  updateNotificationChannel,
  updateAlertRule,
  type AlertRule,
  type AlertRulePayload,
  type NotificationChannel,
  type NotificationChannelPayload,
} from "../../tasks/api";

const METRICS = [
  "eval_regression_triggered",
  "subagent_budget_exceeded_count",
  "tool_adapter_failure_rate",
  "total_cost_spike_ratio",
];
const COMPARATORS: AlertRulePayload["comparator"][] = [">", "<", ">=", "<=", "=="];
const SEVERITIES: AlertRulePayload["severity"][] = ["info", "warning", "critical"];

const DEFAULT_FORM: AlertRulePayload = {
  name: "",
  metric: "subagent_budget_exceeded_count",
  comparator: ">",
  threshold: 1,
  window_seconds: 300,
  enabled: true,
  severity: "warning",
  notification_channels_json: ["in_app"],
};

export function AlertRulesPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<AlertRule | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null);
  const [channelDialogOpen, setChannelDialogOpen] = useState(false);
  const [form, setForm] = useState<AlertRulePayload>(DEFAULT_FORM);
  const rules = useQuery({ queryKey: ["observability", "alert-rules"], queryFn: listAlertRules });
  const channels = useQuery({
    queryKey: ["observability", "notification-channels"],
    queryFn: listNotificationChannels,
  });
  const events = useQuery({
    queryKey: ["observability", "alert-events"],
    queryFn: () => listAlertEvents({ limit: 80 }),
    refetchInterval: 20_000,
  });

  const saveRule = useMutation({
    mutationFn: () => (editing ? updateAlertRule(editing.id, form) : createAlertRule(form)),
    onSuccess: async () => {
      setDialogOpen(false);
      setEditing(null);
      notifyFeedback({ tone: "success", title: "告警规则已保存" });
      await queryClient.invalidateQueries({ queryKey: ["observability", "alert-rules"] });
    },
    onError: (error) => {
      notifyFeedback({ tone: "error", title: "保存失败", description: feedbackErrorMessage(error, "请检查规则字段。") });
    },
  });
  const removeRule = useMutation({
    mutationFn: deleteAlertRule,
    onSuccess: async () => {
      notifyFeedback({ tone: "success", title: "告警规则已删除" });
      await queryClient.invalidateQueries({ queryKey: ["observability", "alert-rules"] });
    },
    onError: (error) => {
      notifyFeedback({ tone: "error", title: "删除失败", description: feedbackErrorMessage(error, "系统默认规则需要先保存为组织规则。") });
    },
  });
  const saveChannel = useMutation({
    mutationFn: (payload: NotificationChannelPayload) =>
      editingChannel
        ? updateNotificationChannel(editingChannel.id, payload)
        : createNotificationChannel(payload),
    onSuccess: async () => {
      setChannelDialogOpen(false);
      setEditingChannel(null);
      notifyFeedback({ tone: "success", title: "通知通道已保存" });
      await queryClient.invalidateQueries({ queryKey: ["observability", "notification-channels"] });
    },
    onError: (error) => {
      notifyFeedback({ tone: "error", title: "通道保存失败", description: feedbackErrorMessage(error, "请检查通道配置。") });
    },
  });
  const removeChannel = useMutation({
    mutationFn: deleteNotificationChannel,
    onSuccess: async () => {
      notifyFeedback({ tone: "success", title: "通知通道已删除" });
      await queryClient.invalidateQueries({ queryKey: ["observability", "notification-channels"] });
    },
    onError: (error) => {
      notifyFeedback({ tone: "error", title: "通道删除失败", description: feedbackErrorMessage(error, "请稍后重试。") });
    },
  });
  const evaluate = useMutation({
    mutationFn: evaluateAlertRules,
    onSuccess: async (result) => {
      notifyFeedback({
        tone: result.items.length ? "warning" : "success",
        title: result.items.length ? "告警已触发" : "未触发告警",
        description: result.items[0]?.message,
      });
      await queryClient.invalidateQueries({ queryKey: ["observability", "alert-events"] });
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(DEFAULT_FORM);
    setDialogOpen(true);
  };
  const openEdit = (rule: AlertRule) => {
    setEditing(rule);
    setForm({
      name: rule.name,
      metric: rule.metric,
      comparator: rule.comparator,
      threshold: rule.threshold,
      window_seconds: rule.window_seconds,
      enabled: rule.enabled,
      severity: rule.severity,
      notification_channels_json: rule.notification_channels_json.length ? rule.notification_channels_json : ["in_app"],
    });
    setDialogOpen(true);
  };
  const activeAlerts = events.data?.items.filter((event) => event.status === "active") ?? [];
  const channelItems = channels.data?.items ?? [];

  return (
    <ConsoleShell title="告警规则">
      <div className="space-y-4 bg-slate-50/70 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Link to="/observability" className="hover:text-slate-900">观测</Link>
            <span>/</span>
            <span className="font-medium text-slate-900">告警</span>
            <Badge tone={activeAlerts.length ? "failed" : "success"}>{activeAlerts.length} 活跃</Badge>
          </div>
          <div className="flex gap-2">
            <Button onClick={() => evaluate.mutate()} disabled={evaluate.isPending}>
              <Play className="h-3.5 w-3.5" /> 评估一次
            </Button>
            <Button variant="primary" onClick={openCreate}>
              <Plus className="h-3.5 w-3.5" /> 新规则
            </Button>
          </div>
        </div>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Bell className="h-4 w-4" /> 规则列表
            </div>
            <span className="text-xs text-slate-500">{rules.data?.items.length ?? 0} 条规则</span>
          </CardHeader>
          <div className="overflow-x-auto">
            <Table className="min-w-[920px]">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <Th>规则</Th>
                  <Th>指标</Th>
                  <Th>条件</Th>
                  <Th>窗口</Th>
                  <Th>级别</Th>
                  <Th>状态</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {(rules.data?.items ?? []).map((rule) => (
                  <tr key={rule.id} className="border-t border-slate-100">
                    <Td>
                      <div className="font-medium text-slate-900">{rule.name}</div>
                      <div className="mt-1 font-mono text-[10px] text-slate-400">{rule.id}</div>
                    </Td>
                    <Td className="font-mono text-[11px]">{rule.metric}</Td>
                    <Td>{rule.comparator} {rule.threshold}</Td>
                    <Td>{rule.window_seconds}s</Td>
                    <Td><Badge tone={rule.severity === "critical" ? "failed" : rule.severity === "warning" ? "warning" : "info"}>{rule.severity}</Badge></Td>
                    <Td><Badge tone={rule.enabled ? "success" : "neutral"}>{rule.enabled ? "启用" : "停用"}</Badge></Td>
                    <Td>
                      <div className="flex justify-end gap-2">
                        <Button className="w-8 px-0" aria-label="编辑" onClick={() => openEdit(rule)}><Pencil className="h-3.5 w-3.5" /></Button>
                        {rule.organization_id ? (
                          <Button variant="danger" className="w-8 px-0" aria-label="删除" onClick={() => removeRule.mutate(rule.id)}><Trash2 className="h-3.5 w-3.5" /></Button>
                        ) : null}
                      </div>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Send className="h-4 w-4" /> 外部通知通道
            </div>
            <Button
              onClick={() => {
                setEditingChannel(null);
                setChannelDialogOpen(true);
              }}
            >
              <Plus className="h-3.5 w-3.5" /> 新通道
            </Button>
          </CardHeader>
          <div className="divide-y divide-slate-100">
            {channelItems.map((channel) => (
              <div key={channel.id} className="grid grid-cols-[1fr_auto] gap-3 px-3 py-3 text-xs">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium text-slate-900">{channel.name}</span>
                    <Badge tone={channel.verified ? "success" : "warning"}>
                      {channel.verified ? "已验证" : "未验证"}
                    </Badge>
                    <Badge tone="info">{channel.kind}</Badge>
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-slate-400">
                    selector: {channelSelector(channel)}
                  </div>
                </div>
                <div className="flex items-center justify-end gap-2">
                  <Button
                    className="w-8 px-0"
                    aria-label="编辑通道"
                    onClick={() => {
                      setEditingChannel(channel);
                      setChannelDialogOpen(true);
                    }}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="danger"
                    className="w-8 px-0"
                    aria-label="删除通道"
                    onClick={() => removeChannel.mutate(channel.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
            {!channels.isLoading && channelItems.length === 0 ? (
              <div className="p-10 text-center text-xs text-slate-500">
                暂无外部通知通道；告警仍会通过 in_app 记录。
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <CardHeader>
            <div className="text-sm font-semibold text-slate-900">告警事件</div>
            <span className="text-xs text-slate-500">最近 {events.data?.items.length ?? 0} 条</span>
          </CardHeader>
          <div className="divide-y divide-slate-100">
            {(events.data?.items ?? []).map((event) => (
              <div key={event.id} className="grid grid-cols-[120px_1fr_160px] gap-3 px-3 py-3 text-xs">
                <Badge tone={event.severity === "critical" ? "failed" : "warning"}>{event.severity}</Badge>
                <div>
                  <div className="font-medium text-slate-900">{event.message}</div>
                  <div className="mt-1 font-mono text-[10px] text-slate-400">{event.metric}</div>
                </div>
                <div className="text-right text-slate-500">{formatShortDate(event.triggered_at)}</div>
              </div>
            ))}
            {!events.isLoading && !events.data?.items.length ? <div className="p-10 text-center text-xs text-slate-500">暂无告警事件</div> : null}
          </div>
        </Card>
      </div>

      <ConfigDialog open={dialogOpen} title={editing ? "编辑告警规则" : "新建告警规则"} onClose={() => setDialogOpen(false)}>
        <div className="space-y-4">
          <Label title="规则名称"><Input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} /></Label>
          <div className="grid grid-cols-2 gap-3">
            <Label title="指标">
              <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm" value={form.metric} onChange={(event) => setForm({ ...form, metric: event.target.value })}>
                {METRICS.map((metric) => <option key={metric} value={metric}>{metric}</option>)}
              </select>
            </Label>
            <Label title="比较符">
              <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm" value={form.comparator} onChange={(event) => setForm({ ...form, comparator: event.target.value as AlertRulePayload["comparator"] })}>
                {COMPARATORS.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </Label>
            <Label title="阈值"><Input type="number" value={form.threshold} onChange={(event) => setForm({ ...form, threshold: Number(event.target.value) })} /></Label>
            <Label title="窗口秒数"><Input type="number" value={form.window_seconds} onChange={(event) => setForm({ ...form, window_seconds: Number(event.target.value) })} /></Label>
            <Label title="级别">
              <select className="h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm" value={form.severity} onChange={(event) => setForm({ ...form, severity: event.target.value as AlertRulePayload["severity"] })}>
                {SEVERITIES.map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </Label>
            <label className="flex items-center gap-2 pt-6 text-sm text-slate-700">
              <input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} /> 启用
            </label>
          </div>
          <div className="rounded-md border border-slate-100 bg-slate-50 p-3">
            <div className="mb-2 text-xs font-semibold text-slate-700">通知通道</div>
            <div className="grid gap-2 text-xs text-slate-700">
              {["in_app", ...channelItems.map(channelSelector)].map((selector) => (
                <label key={selector} className="inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={form.notification_channels_json.includes(selector)}
                    onChange={(event) => {
                      const selected = new Set(form.notification_channels_json);
                      if (event.target.checked) {
                        selected.add(selector);
                      } else {
                        selected.delete(selector);
                      }
                      setForm({
                        ...form,
                        notification_channels_json: selected.size ? Array.from(selected) : ["in_app"],
                      });
                    }}
                  />
                  <span className="font-mono">{selector}</span>
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setDialogOpen(false)}>取消</Button>
            <Button variant="primary" disabled={!form.name.trim() || saveRule.isPending} onClick={() => saveRule.mutate()}>保存</Button>
          </div>
        </div>
      </ConfigDialog>
      <ConfigDialog
        open={channelDialogOpen}
        title={editingChannel ? "编辑通知通道" : "新建通知通道"}
        onClose={() => setChannelDialogOpen(false)}
      >
        <NotificationChannelForm
          initial={editingChannel}
          pending={saveChannel.isPending}
          onCancel={() => setChannelDialogOpen(false)}
          onSubmit={(payload) => saveChannel.mutate(payload)}
        />
      </ConfigDialog>
    </ConsoleShell>
  );
}

function channelSelector(channel: NotificationChannel) {
  if (channel.kind === "email") {
    return `email:${String(channel.config_json.to ?? "*")}`;
  }
  if (channel.kind === "slack") {
    return `slack:${String(channel.config_json.channel ?? channel.name)}`;
  }
  return `webhook:${channel.name}`;
}

function Label({ title, children }: { title: string; children: ReactNode }) {
  return (
    <label className="block text-xs font-medium text-slate-600">
      {title}
      <div className="mt-1">{children}</div>
    </label>
  );
}
