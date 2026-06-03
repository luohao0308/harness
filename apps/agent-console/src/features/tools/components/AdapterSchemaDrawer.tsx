import { FileJson2 } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { ConfigDialog } from "../../../components/ui/config-dialog";
import { type AdapterMetadata } from "../../tasks/api";
import { AdapterTryItForm } from "./AdapterTryItForm";

export function AdapterSchemaDrawer({
  adapter,
  agentId = "default",
  open,
  onClose,
}: {
  adapter: AdapterMetadata | null;
  agentId?: string;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <ConfigDialog
      open={open && adapter !== null}
      title={adapter?.slug ?? "Adapter Schema"}
      description="真实工具 Adapter 的输入、输出和审计快照信息。"
      onClose={onClose}
      className="max-w-5xl"
    >
      {adapter ? (
        <div className="grid gap-4 text-xs">
          <div className="flex flex-wrap gap-2">
            <Badge tone="info">{adapter.server_label}.{adapter.method}</Badge>
            <Badge tone={adapter.requires_secret ? "warning" : "success"}>
              {adapter.requires_secret ? "需要密钥" : "无需密钥"}
            </Badge>
            <Badge tone="neutral">{adapter.version}</Badge>
            <Badge tone="neutral">sha {adapter.adapter_sha256.slice(0, 8)}</Badge>
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <SchemaBlock title="Input Schema" value={adapter.input_schema} />
            <SchemaBlock title="Output Schema" value={adapter.output_schema} />
          </div>
          <div className="grid gap-2 rounded-md border border-slate-200 bg-white p-3">
            <div className="inline-flex items-center gap-1.5 font-semibold text-slate-900">
              <FileJson2 className="h-3.5 w-3.5" />
              审计哈希
            </div>
            <div className="grid gap-1 font-mono text-[11px] text-slate-600 md:grid-cols-3">
              <span>adapter {adapter.adapter_sha256}</span>
              <span>input {adapter.input_schema_sha256}</span>
              <span>output {adapter.output_schema_sha256}</span>
            </div>
          </div>
          <AdapterTryItForm adapter={adapter} agentId={agentId} />
          <div>
            <Button type="button" variant="ghost" onClick={onClose}>
              关闭
            </Button>
          </div>
        </div>
      ) : null}
    </ConfigDialog>
  );
}

function SchemaBlock({ title, value }: { title: string; value: Record<string, unknown> }) {
  return (
    <div className="grid gap-2">
      <div className="font-semibold text-slate-900">{title}</div>
      <pre className="max-h-80 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-3 font-mono text-[11px] text-slate-700">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
