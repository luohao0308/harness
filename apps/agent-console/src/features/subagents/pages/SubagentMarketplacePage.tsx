import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Download, Store, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { ConsoleShell } from "../../../app/ConsoleShell";
import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { feedbackErrorMessage, notifyFeedback } from "../../../components/ui/feedback-toast";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { formatShortDate } from "../../../lib/utils";
import {
  approveSpecialistMarketplaceListing,
  installSpecialistMarketplaceListing,
  listSpecialistMarketplaceListings,
  type SpecialistMarketplaceListing,
} from "../../tasks/api";

export function SubagentMarketplacePage() {
  const { text } = useI18n();
  const queryClient = useQueryClient();
  const listingsQuery = useQuery({
    queryKey: ["subagent-marketplace", "listings"],
    queryFn: () => listSpecialistMarketplaceListings({ include_unverified: true }),
  });
  const listings = listingsQuery.data?.items ?? [];
  const counts = useMemo(
    () => ({
      total: listings.length,
      verified: listings.filter((item) => item.verified).length,
      installed: listings.filter((item) => item.installed).length,
      downloads: listings.reduce((sum, item) => sum + item.download_count, 0),
    }),
    [listings],
  );
  const installMutation = useMutation({
    mutationFn: (listingId: string) => installSpecialistMarketplaceListing(listingId),
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
    mutationFn: (listingId: string) => approveSpecialistMarketplaceListing(listingId, true),
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

  return (
    <ConsoleShell title={text("专家市场", "Specialist Marketplace")}>
      <div className="mx-auto max-w-[1440px] space-y-4 p-6">
        <section className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="inline-flex items-center gap-2 text-lg font-semibold tracking-tight text-slate-900">
              <Store className="h-4 w-4" /> {text("子代理专家市场", "Subagent Specialist Marketplace")}
            </div>
            <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">
              {text(
                "跨组织浏览、审核并安装已签名的专家模板；安装后会生成当前组织的独立专家副本。",
                "Browse, approve, and install signed specialist templates across organizations; installs create isolated org-local copies.",
              )}
            </p>
          </div>
          <Button>
            <Link to="/subagent-specialists">
              <ShieldCheck className="h-3.5 w-3.5" /> {text("专家库", "Specialists")}
            </Link>
          </Button>
        </section>

        <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label={text("Listing", "Listings")} value={counts.total} />
          <Metric label={text("已审核", "Verified")} value={counts.verified} />
          <Metric label={text("已安装", "Installed")} value={counts.installed} />
          <Metric label={text("安装次数", "Downloads")} value={counts.downloads} />
        </section>

        <Card className="overflow-hidden">
          <CardHeader>
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-slate-900">
              <BadgeCheck className="h-4 w-4" /> {text("市场条目", "Marketplace Listings")}
            </div>
            <span className="text-xs text-slate-500">
              {listingsQuery.isLoading ? text("加载中...", "Loading...") : `${listings.length}`}
            </span>
          </CardHeader>
          <Table>
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <Th>{text("专家", "Specialist")}</Th>
                <Th>{text("作者", "Author")}</Th>
                <Th>{text("版本", "Version")}</Th>
                <Th>{text("审核", "Review")}</Th>
                <Th>{text("安装", "Install")}</Th>
                <Th>{text("下载", "Downloads")}</Th>
                <Th>{text("更新", "Updated")}</Th>
                <Th>{text("操作", "Actions")}</Th>
              </tr>
            </thead>
            <tbody>
              {listings.map((listing) => (
                <ListingRow
                  key={listing.id}
                  listing={listing}
                  installPending={installMutation.isPending}
                  approvePending={approveMutation.isPending}
                  onInstall={() => installMutation.mutate(listing.id)}
                  onApprove={() => approveMutation.mutate(listing.id)}
                />
              ))}
              {listings.length === 0 && (
                <tr>
                  <Td colSpan={8} className="py-10 text-center text-slate-500">
                    {text("暂无专家市场条目。", "No specialist marketplace listings yet.")}
                  </Td>
                </tr>
              )}
            </tbody>
          </Table>
        </Card>
      </div>
    </ConsoleShell>
  );
}

function ListingRow({
  listing,
  installPending,
  approvePending,
  onInstall,
  onApprove,
}: {
  listing: SpecialistMarketplaceListing;
  installPending: boolean;
  approvePending: boolean;
  onInstall: () => void;
  onApprove: () => void;
}) {
  return (
    <tr className="border-t border-slate-100 hover:bg-slate-50/60">
      <Td>
        <Link to={`/subagent-marketplace/${listing.id}`} className="font-semibold text-slate-900">
          {listing.display_name}
        </Link>
        <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-slate-500">
          <span className="font-mono">{listing.slug}</span>
          <span className="max-w-[320px] truncate">{listing.description}</span>
        </div>
      </Td>
      <Td className="text-slate-600">{listing.author_name}</Td>
      <Td className="font-mono text-slate-700">{listing.version}</Td>
      <Td>
        <Badge tone={listing.verified ? "success" : "warning"}>
          {listing.verified ? "已审核" : "待审核"}
        </Badge>
      </Td>
      <Td>
        <Badge tone={listing.installed ? "info" : "neutral"}>
          {listing.installed ? "已安装" : "未安装"}
        </Badge>
      </Td>
      <Td className="font-mono text-slate-600">{listing.download_count}</Td>
      <Td className="font-mono text-slate-500">{formatShortDate(listing.updated_at)}</Td>
      <Td>
        <div className="flex items-center gap-2">
          <Button type="button" disabled={listing.verified || approvePending} onClick={onApprove}>
            <BadgeCheck className="h-3.5 w-3.5" /> 审核
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={!listing.verified || listing.installed || installPending}
            onClick={onInstall}
          >
            <Download className="h-3.5 w-3.5" /> 安装
          </Button>
        </div>
      </Td>
    </tr>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-3">
      <div className="text-[11px] font-medium text-slate-500">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold text-slate-900">{value}</div>
    </Card>
  );
}
