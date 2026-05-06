import { ShieldCheck } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { useI18n } from "../../../lib/i18n";

export function PolicyBadge({ requiresSandbox }: { requiresSandbox: boolean }) {
  const { text } = useI18n();
  return (
    <Badge tone={requiresSandbox ? "warning" : "success"}>
      <ShieldCheck className="h-3 w-3" />
      {requiresSandbox ? text("需要沙箱", "Sandbox Required") : text("低风险", "Low Risk")}
    </Badge>
  );
}
