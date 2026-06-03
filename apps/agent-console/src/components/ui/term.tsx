import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

export function TermHint({
  children,
  description,
  className,
  descriptionClassName,
}: {
  children: ReactNode;
  description: string;
  className?: string;
  descriptionClassName?: string;
}) {
  return (
    <span className={cn("inline-flex min-w-0 flex-col leading-tight", className)} title={description}>
      <span className="min-w-0 truncate">{children}</span>
      <span className={cn("mt-0.5 text-[10px] font-normal leading-3 text-slate-400", descriptionClassName)}>
        {description}
      </span>
    </span>
  );
}

export function InlineTermHint({
  term,
  description,
  className,
}: {
  term: string;
  description: string;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-baseline gap-1", className)} title={description}>
      <span>{term}</span>
      <span className="text-[10px] font-normal text-slate-400">{description}</span>
    </span>
  );
}

export const TERM_DEFINITIONS: Record<string, string> = {
  Adapter: "把外部服务接成 Harness 工具的运行适配层",
  Contract: "Eval 或 Specialist 输出必须满足的结构化约束",
  Grounding: "回答必须绑定到检索、引用和策略证据",
  Manifest: "记录上下文、工具、检索或能力版本的审计清单",
  MCP: "Model Context Protocol，用于连接外部工具和资源",
  RAG: "Retrieval-Augmented Generation，基于文档检索增强回答",
  Sandbox: "隔离执行工具和代码的受控运行环境",
  Specialist: "有角色、工具白名单和输出 schema 的子 Agent 模板",
  Token: "模型上下文和输出计费的基本单位",
  Trace: "把 Run、模型调用、工具调用和事件串起来的观测线索",
  WarmPool: "预热沙箱池，降低工具执行冷启动成本",
};

const TERM_PATTERN = new RegExp(
  `\\b(${Object.keys(TERM_DEFINITIONS)
    .sort((a, b) => b.length - a.length)
    .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|")})\\b`,
  "g",
);

export function JargonText({ children }: { children: string }) {
  const parts = children.split(TERM_PATTERN);
  return (
    <>
      {parts.map((part, index) => {
        const description = TERM_DEFINITIONS[part];
        if (!description) {
          return part;
        }
        return (
          <span
            key={`${part}-${index}`}
            className="cursor-help border-b border-dotted border-slate-400 text-slate-900"
            title={description}
          >
            {part}
          </span>
        );
      })}
    </>
  );
}
