import { ShieldCheck } from "lucide-react";

import { Badge } from "../../../components/ui/badge";

export function PolicyBadge({ requiresSandbox }: { requiresSandbox: boolean }) {
  return (
    <Badge tone={requiresSandbox ? "warning" : "success"}>
      <ShieldCheck className="h-3 w-3" />
      {requiresSandbox ? "需要沙箱" : "低风险"}
    </Badge>
  );
}
