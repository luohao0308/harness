import { Link } from "react-router-dom";

import { Badge, statusTone } from "../../../components/ui/badge";
import { EmptyState } from "../../../components/ui/EmptyState";
import { formatShortDate } from "../../../lib/utils";
import { statusLabel } from "../../../lib/labels";
import type { Task } from "../../tasks/api";
import { ListChecks } from "lucide-react";

export function RecentActivityList({ items }: { items: Task[] }) {
  if (!items.length) {
    return (
      <EmptyState
        icon={<ListChecks className="h-5 w-5" />}
        title="暂无近期运行"
        description="启动一次任务后，最近活动会在这里显示运行状态和跳转入口。"
        actions={[{ label: "打开工作台", href: "/agents/default/workspace", primary: true }]}
      />
    );
  }

  return (
    <div className="divide-y divide-slate-100">
      {items.slice(0, 10).map((run) => (
        <Link
          key={run.id}
          to={`/runs/${run.id}`}
          className="grid grid-cols-[1fr_auto] gap-3 px-3 py-3 text-xs transition hover:bg-slate-50"
        >
          <div className="min-w-0">
            <div className="truncate font-medium text-slate-900">{run.title}</div>
            <div className="mt-1 truncate text-[11px] text-slate-500">{run.goal}</div>
          </div>
          <div className="text-right">
            <Badge tone={statusTone(run.status)}>{statusLabel(run.status)}</Badge>
            <div className="mt-1 font-mono text-[10px] text-slate-400">
              {formatShortDate(run.updated_at)}
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
