import { useQuery } from "@tanstack/react-query";
import { Activity, AlertCircle, CheckCircle2 } from "lucide-react";
import type { ReactNode } from "react";

import { Badge, type BadgeTone } from "../../../components/ui/badge";
import { getAdapterHealth, type AdapterHealth } from "../../tasks/api";

export function AdapterHealthBadge({
  slug,
  agentId = "default",
  compact = false,
}: {
  slug: string;
  agentId?: string;
  compact?: boolean;
}) {
  const health = useQuery({
    queryKey: ["adapter-health", slug, agentId],
    queryFn: () => getAdapterHealth(slug, agentId),
    enabled: Boolean(slug),
    staleTime: 30_000,
    retry: false,
  });
  const state = adapterHealthState(health.data, health.isFetching, health.isError);

  return (
    <Badge tone={state.tone} className={compact ? "px-1.5" : undefined}>
      {state.icon}
      <span title={state.title}>{compact ? state.shortLabel : state.label}</span>
    </Badge>
  );
}

export function adapterHealthState(
  health: AdapterHealth | undefined,
  fetching: boolean,
  errored: boolean,
): { label: string; shortLabel: string; tone: BadgeTone; title: string; icon: ReactNode } {
  if (fetching && !health) {
    return {
      label: "健康检查中",
      shortLabel: "检查",
      tone: "running",
      title: "正在探测 Adapter 健康状态",
      icon: <Activity className="h-3 w-3" />,
    };
  }
  if (errored) {
    return {
      label: "健康未知",
      shortLabel: "未知",
      tone: "warning",
      title: "健康检查请求失败",
      icon: <AlertCircle className="h-3 w-3" />,
    };
  }
  if (health?.ok) {
    return {
      label: `健康 · ${health.latency_ms}ms`,
      shortLabel: "健康",
      tone: "success",
      title: health.message,
      icon: <CheckCircle2 className="h-3 w-3" />,
    };
  }
  return {
    label: "需配置",
    shortLabel: "需配置",
    tone: "warning",
    title: health?.message ?? "Adapter 未返回健康状态",
    icon: <AlertCircle className="h-3 w-3" />,
  };
}
