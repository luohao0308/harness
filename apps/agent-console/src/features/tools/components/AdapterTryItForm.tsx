import { useMemo, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Play } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { feedbackErrorMessage } from "../../../components/ui/feedback-toast";
import { Textarea } from "../../../components/ui/input";
import { tryAdapter, type AdapterMetadata } from "../../tasks/api";

export function AdapterTryItForm({
  adapter,
  agentId = "default",
}: {
  adapter: AdapterMetadata;
  agentId?: string;
}) {
  const initialInput = useMemo(() => JSON.stringify(sampleInputForAdapter(adapter), null, 2), [adapter]);
  const [inputText, setInputText] = useState(initialInput);
  const mutation = useMutation({
    mutationFn: () =>
      tryAdapter({
        agent_id: agentId,
        tool_name: adapter.slug,
        input_json: JSON.parse(inputText) as Record<string, unknown>,
      }),
  });

  return (
    <div className="grid gap-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-semibold text-slate-900">试调输入</div>
        <Badge tone="info">{agentId}</Badge>
      </div>
      <Textarea
        aria-label={`${adapter.slug} 试调输入`}
        className="min-h-32 font-mono text-xs"
        value={inputText}
        onChange={(event) => setInputText(event.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <Button type="button" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <Play className="h-3.5 w-3.5" />
          {mutation.isPending ? "试调中" : "试调"}
        </Button>
        <Button type="button" variant="ghost" onClick={() => setInputText(initialInput)}>
          重置
        </Button>
      </div>
      {mutation.error ? (
        <div className="rounded border border-red-100 bg-red-50 p-2 text-xs text-red-800">
          {feedbackErrorMessage(mutation.error, "Adapter 试调失败。")}
        </div>
      ) : null}
      {mutation.data ? (
        <pre className="max-h-72 overflow-auto rounded border border-slate-200 bg-white p-3 font-mono text-[11px] text-slate-700">
          {JSON.stringify(mutation.data.output, null, 2)}
        </pre>
      ) : null}
    </div>
  );
}

function sampleInputForAdapter(adapter: AdapterMetadata): Record<string, unknown> {
  if (adapter.slug.includes("list_issues")) return { repo: "owner/repo", state: "open", limit: 5 };
  if (adapter.slug.includes("get_issue")) return { repo: "owner/repo", number: 1, include_comments: true };
  if (adapter.slug.includes("list_pulls")) return { repo: "owner/repo", state: "open", limit: 5 };
  if (adapter.slug.includes("get_pull")) return { repo: "owner/repo", number: 1 };
  if (adapter.slug.includes("search_code")) return { query: "ToolRunner", repo: "owner/repo", language: "python", limit: 5 };
  if (adapter.slug.includes("search_messages")) return { query: "release", limit: 5 };
  if (adapter.slug.includes("list_channels")) return { types: "public_channel,private_channel", limit: 20 };
  if (adapter.slug.includes("get_thread")) return { channel: "C123", thread_ts: "1710000000.000000" };
  if (adapter.slug.includes("read_file")) return { path: "README.md", max_bytes: 4096 };
  if (adapter.slug.includes("list_files")) return { path: ".", pattern: "*", max_entries: 50 };
  if (adapter.slug.includes("write_file")) return { path: "output.txt", content: "hello" };
  if (adapter.slug.includes("delete_file")) return { path: "output.txt" };
  return { query: "release readiness", limit: 3 };
}
