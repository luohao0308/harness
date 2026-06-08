import { Play } from "lucide-react";

import { Badge } from "../../../components/ui/badge";
import { Button } from "../../../components/ui/button";
import { Card, CardHeader } from "../../../components/ui/card";
import { MenuSelect, type MenuSelectOption } from "../../../components/ui/menu-select";
import { Table, Td, Th } from "../../../components/ui/table";
import { useI18n } from "../../../lib/i18n";
import { statusLabel } from "../../../lib/labels";
import { formatShortDate } from "../../../lib/utils";
import type { EvalCase } from "../../tasks/api";

interface EvalCaseListProps {
  cases: EvalCase[];
  isLoading: boolean;
  agentId: string;
  onAgentIdChange: (value: string) => void;
  agentOptions: MenuSelectOption[];
  canRunEval: boolean;
  onRunEval: () => void;
}

export function EvalCaseList({
  cases,
  isLoading,
  agentId,
  onAgentIdChange,
  agentOptions,
  canRunEval,
  onRunEval,
}: EvalCaseListProps) {
  const { text } = useI18n();

  return (
    <Card className="overflow-visible">
      <CardHeader className="flex-col items-start gap-3 sm:flex-row sm:items-center">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-slate-900">
            {text("用例队列", "Case Queue")}
          </div>
          <div className="max-w-[22rem] text-[11px] leading-4 text-slate-500">
            {text(
              "每个用例都来自真实运行或显式输入",
              "Every case is backed by a run or explicit input",
            )}
          </div>
        </div>
        <div className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:justify-end">
          <MenuSelect
            ariaLabel={text("选择评测智能体", "Select eval agent")}
            value={agentId}
            onChange={onAgentIdChange}
            options={agentOptions}
            placeholder={text("选择智能体", "Select agent")}
            size="compact"
            showSelectedDescription={false}
            className="min-w-0 flex-1 sm:w-40 sm:flex-none"
            buttonClassName="h-8 rounded-md px-2.5 py-1.5 shadow-none"
            menuClassName="w-[min(16rem,calc(100vw-3rem))] max-h-64"
          />
          <Button
            variant="primary"
            disabled={!canRunEval}
            onClick={onRunEval}
            className="h-8 shrink-0 gap-1.5 whitespace-nowrap px-3"
          >
            <Play className="h-3.5 w-3.5" />
            {text("运行评测", "Run Eval")}
          </Button>
        </div>
      </CardHeader>
      <div className="overflow-x-auto">
        <Table className="min-w-[38rem]">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <Th>用例</Th>
              <Th>来源运行</Th>
              <Th>期望</Th>
              <Th>标签</Th>
              <Th>创建时间</Th>
            </tr>
          </thead>
          <tbody>
            {cases.map((item) => (
              <tr key={item.id} className="border-t border-slate-100">
                <Td className="font-mono text-slate-500">{item.id.slice(0, 8)}</Td>
                <Td className="font-mono text-slate-600">
                  {item.source_task_id ? (
                    <a
                      href={`/runs/${item.source_task_id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {item.source_task_id.slice(0, 8)}
                    </a>
                  ) : (
                    "手动录入"
                  )}
                </Td>
                <Td className="font-mono text-slate-600">
                  <Badge>{statusLabel(String(item.expected_json.status ?? "自定义"))}</Badge>
                </Td>
                <Td>{item.tags_json.join(", ")}</Td>
                <Td className="font-mono text-slate-500">{formatShortDate(item.created_at)}</Td>
              </tr>
            ))}
            {!isLoading && cases.length === 0 && (
              <tr>
                <Td colSpan={5} className="py-12 text-center text-slate-500">
                  {text(
                    "选择数据集后保存运行作为评测用例",
                    "Select a dataset and save a run as a case",
                  )}
                </Td>
              </tr>
            )}
          </tbody>
        </Table>
      </div>
    </Card>
  );
}
