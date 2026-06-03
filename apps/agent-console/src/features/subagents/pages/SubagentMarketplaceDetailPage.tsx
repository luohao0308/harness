import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, ChevronRight, Download, FileJson, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import {
  approveSpecialistMarketplaceListing,
  getSpecialistMarketplaceListing,
  installSpecialistMarketplaceListing,
} from "../../tasks/api";

export function SubagentMarketplaceDetailPage() {
  const { text } = useI18n();
  const { listingId } = useParams();
  const queryClient = useQueryClient();
  const listingQuery = useQuery({
    queryKey: ["subagent-marketplace", "listing", listingId],
    queryFn: () => getSpecialistMarketplaceListing(listingId!),
    enabled: Boolean(listingId),
  });
  const listing = listingQuery.data;
  const installMutation = useMutation({
    mutationFn: () => installSpecialistMarketplaceListing(listingId!),
    onSuccess: async (installation) => {
      notifyFeedback({
        tone: "success",
        title: text("专家已安装", "Specialist installed"),
        description: installation.specialist?.slug ?? installation.installed_specialist_id,
      });
      await queryClient.invalidateQueries({ queryKey: ["subagent-marketplace"] });
      await queryClient.invalidateQueries({ queryKey: ["subagent-specialists"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("安装失败", "Install failed"),
        description: feedbackErrorMessage(error, text("请确认 listing 已审核且未重复安装。", "Confirm the listing is verified and not already installed.")),
      });
    },
  });
  const approveMutation = useMutation({
    mutationFn: () => approveSpecialistMarketplaceListing(listingId!, true),
    onSuccess: async () => {
      notifyFeedback({ tone: "success", title: text("已审核通过", "Listing approved") });
      await queryClient.invalidateQueries({ queryKey: ["subagent-marketplace"] });
    },
    onError: (error) => {
      notifyFeedback({
        tone: "error",
        title: text("审核失败", "Approval failed"),
        description: feedbackErrorMessage(error, text("需要管理员权限。", "Admin permission is required.")),
      });
    },
  });

  if (!listing) {
    return (
      <ConsoleShell title={text("专家市场 / 详情", "Marketplace / Detail")}>
        <div className="p-6 text-sm text-slate-500">
          {listingQuery.isError
            ? text("专家市场条目加载失败。", "Failed to load marketplace listing.")
            : text("专家市场条目加载中...", "Loading marketplace listing...")}
        </div>
      </ConsoleShell>
    );
  }

  return (
    <ConsoleShell title={`${text("专家市场", "Marketplace")} / ${listing.slug}`}>
      <div className="border-b border-slate-200 bg-white px-6 py-5">
        <div className="mb-2 flex items-center gap-2 text-xs text-slate-500">
          <Link to="/subagent-marketplace">{text("专家市场", "Marketplace")}</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-mono">{listing.slug}</span>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="truncate text-xl font-semibold tracking-tight text-slate-900">
                {listing.display_name}
              </h1>
              <Badge tone={listing.verified ? "success" : "warning"}>
                {listing.verified ? text("已审核", "Verified") : text("待审核", "Pending")}
              </Badge>
              <Badge tone={listing.installed ? "info" : "neutral"}>
                {listing.installed ? text("已安装", "Installed") : text("未安装", "Not installed")}
              </Badge>
            </div>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-slate-600">{listing.description}</p>
            <div className="mt-2 flex flex-wrap items-center gap-5 text-xs text-slate-500">
              <span>{text("作者", "Author")} <span className="text-slate-800">{listing.author_name}</span></span>
              <span>Version <span className="font-mono text-slate-800">{listing.version}</span></span>
              <span>{text("下载", "Downloads")} <span className="font-mono text-slate-800">{listing.download_count}</span></span>
              <span>{text("更新", "Updated")} <span className="font-mono text-slate-800">{formatShortDate(listing.updated_at)}</span></span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" disabled={listing.verified || approveMutation.isPending} onClick={() => approveMutation.mutate()}>
              <BadgeCheck className="h-3.5 w-3.5" /> {text("审核", "Approve")}
            </Button>
            <Button
              type="button"
              variant="primary"
              disabled={!listing.verified || listing.installed || installMutation.isPending}
              onClick={() => installMutation.mutate()}
            >
              <Download className="h-3.5 w-3.5" /> {text("安装", "Install")}
            </Button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 p-4">
        <section className="col-span-12 space-y-4 xl:col-span-7">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <FileJson className="h-4 w-4" /> Manifest
              </div>
              <span className="font-mono text-[10px] text-slate-400">{listing.signature.slice(0, 24)}</span>
            </CardHeader>
            <div className="p-3">
              <JsonBlock value={listing.manifest_json} />
            </div>
          </Card>
        </section>
        <aside className="col-span-12 space-y-4 xl:col-span-5">
          <Card>
            <CardHeader>
              <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
                <ShieldCheck className="h-4 w-4" /> {text("信任链", "Trust Chain")}
              </div>
            </CardHeader>
            <div className="space-y-3 p-3 text-xs text-slate-600">
              <KeyValue label="Signature" value={listing.signature} />
              <KeyValue label={text("作者组织", "Author Org")} value={listing.author_org_id ?? "-"} />
              <KeyValue label={text("安装专家", "Installed Specialist")} value={listing.installed_specialist_id ?? "-"} />
            </div>
          </Card>
        </aside>
      </div>
    </ConsoleShell>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[560px] overflow-auto rounded-md bg-slate-950 p-3 text-[11px] leading-relaxed text-slate-100">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-100 bg-slate-50 p-2">
      <div className="text-[11px] font-semibold text-slate-500">{label}</div>
      <div className="mt-1 break-all font-mono text-[11px] text-slate-800">{value}</div>
    </div>
  );
}
