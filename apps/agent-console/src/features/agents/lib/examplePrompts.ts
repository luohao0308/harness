/**
 * Welcome-state example prompts (Req 8.2, 8.3).
 * 3–5 entries, each locale string ≤ 120 characters.
 *
 * Themes covered:
 *   1. ask-help          — generic chat, ask what the agent can do
 *   2. call-tool-bash    — trigger a tool via @-mention
 *   3. create-plan-run   — cross-page prompt hinting at Plan-Act Run creation
 *   4. save-eval-case    — cross-page prompt hinting at Eval Harness
 *   5. view-failed-trace — cross-page prompt hinting at observability
 *
 * Pure module: no React imports, no side effects.
 */

export type ExamplePrompt = {
  id: string;
  zh: string;
  en: string;
};

export const EXAMPLE_PROMPTS: readonly ExamplePrompt[] = [
  {
    id: "ask-help",
    zh: "你能帮我做些什么？简单介绍一下 Harness 最常用的几个使用场景。",
    en: "What can you help with? Give me a short tour of Harness's most common workflows.",
  },
  {
    id: "call-tool-bash",
    zh: "调用 @bash 列出当前目录，并用一段话总结你看到的文件结构。",
    en: "Use @bash to list the current directory and summarize what you see in one paragraph.",
  },
  {
    id: "create-plan-run",
    zh: "帮我创建一个 Plan-Act Run，用来分析 services/api-server 最近的错误日志。",
    en: "Create a Plan-Act Run to analyze the latest error logs in services/api-server.",
  },
  {
    id: "save-eval-case",
    zh: "把当前这段对话保存成 Eval Case，打上 regression 标签并放到默认 rubric 下。",
    en: "Save this conversation as an Eval Case with the regression tag under the default rubric.",
  },
  {
    id: "view-failed-trace",
    zh: "打开 observability，定位最近一条失败的 trace，并简要说明失败原因。",
    en: "Open observability, locate the latest failed trace, and summarize what went wrong.",
  },
] as const;
