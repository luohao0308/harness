import { useEffect, useState } from "react";

import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import type { NotificationChannel, NotificationChannelKind, NotificationChannelPayload } from "../../tasks/api";

type NotificationChannelFormProps = {
  initial?: NotificationChannel | null;
  onSubmit: (payload: NotificationChannelPayload) => void;
  onCancel: () => void;
  pending?: boolean;
};

export function NotificationChannelForm({
  initial,
  onSubmit,
  onCancel,
  pending = false,
}: NotificationChannelFormProps) {
  const [name, setName] = useState(initial?.name ?? "ops-webhook");
  const [kind, setKind] = useState<NotificationChannelKind>(initial?.kind ?? "webhook");
  const [target, setTarget] = useState(String(initial?.config_json.to ?? initial?.config_json.channel ?? ""));
  const [url, setUrl] = useState(String(initial?.config_json.webhook_url ?? initial?.config_json.url ?? ""));
  const [smtpHost, setSmtpHost] = useState(String(initial?.config_json.smtp_host ?? ""));
  const [verified, setVerified] = useState(initial?.verified ?? true);

  useEffect(() => {
    setName(initial?.name ?? "ops-webhook");
    setKind(initial?.kind ?? "webhook");
    setTarget(String(initial?.config_json.to ?? initial?.config_json.channel ?? ""));
    setUrl(String(initial?.config_json.webhook_url ?? initial?.config_json.url ?? ""));
    setSmtpHost(String(initial?.config_json.smtp_host ?? ""));
    setVerified(initial?.verified ?? true);
  }, [initial]);

  const submit = () => {
    const config_json =
      kind === "email"
        ? { to: target, smtp_host: smtpHost, smtp_port: 25 }
        : kind === "slack"
          ? { channel: target, webhook_url: url }
          : { webhook_url: url };
    onSubmit({ name, kind, config_json, verified });
  };

  return (
    <div className="space-y-4">
      <label className="grid gap-1 text-xs font-medium text-slate-600">
        名称
        <Input value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="grid gap-1 text-xs font-medium text-slate-600">
        类型
        <select
          className="h-9 rounded-md border border-slate-200 bg-white px-3 text-sm"
          value={kind}
          onChange={(event) => setKind(event.target.value as NotificationChannelKind)}
        >
          <option value="webhook">Webhook</option>
          <option value="slack">Slack</option>
          <option value="email">Email</option>
        </select>
      </label>
      {kind !== "webhook" ? (
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          {kind === "email" ? "收件地址" : "Slack Channel"}
          <Input value={target} onChange={(event) => setTarget(event.target.value)} />
        </label>
      ) : null}
      {kind === "email" ? (
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          SMTP Host
          <Input value={smtpHost} onChange={(event) => setSmtpHost(event.target.value)} />
        </label>
      ) : (
        <label className="grid gap-1 text-xs font-medium text-slate-600">
          Webhook URL
          <Input value={url} onChange={(event) => setUrl(event.target.value)} />
        </label>
      )}
      <label className="inline-flex items-center gap-2 text-xs text-slate-700">
        <input type="checkbox" checked={verified} onChange={(event) => setVerified(event.target.checked)} />
        标记为已验证
      </label>
      <div className="flex justify-end gap-2">
        <Button onClick={onCancel}>取消</Button>
        <Button variant="primary" disabled={pending || !name.trim()} onClick={submit}>
          保存
        </Button>
      </div>
    </div>
  );
}
