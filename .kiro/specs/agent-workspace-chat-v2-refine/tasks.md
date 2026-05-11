# Implementation Plan: agent-workspace-chat-v2-refine

> Convert the feature design into a series of prompts for a code-generation LLM that will implement each step with incremental progress. Make sure that each prompt builds on the previous prompts, and ends with wiring things together. There should be no hanging or orphaned code that isn't integrated into a previous step. Focus ONLY on tasks that involve writing, modifying, or testing code.

## Overview

本计划严格基于 `design.md` §Module Layout 落地 v2 的 UX 打磨与流式修复。语言沿用 v1 的 **TypeScript 严格模式**（React 18 + Vite 6 + Tailwind 3.4 + Zustand 5 + lucide-react），**不新增 runtime 依赖**，**不改 SSE 契约**，`useWorkspaceStore` / `AgentChatStreamEvent` / `streamAgentChatRun` 保持 additive 兼容。

所有改动限定在 `apps/agent-console/`。执行顺序按"纯函数 lib → hooks/store → 基础组件 → 组合组件 → 主视口 → 页面集成 → 属性测试 → 最终 checkpoint"的依赖链推进，9 个 wave 内部任务可并行。

## Tasks

- [x] 1. Wave 0 — Skeleton & controller signature

  - [x] 1.1 建立 v2 目录骨架与 `driveBranch` 签名占位
    - **产出（新增文件占位，可先写空导出）**:
      - `apps/agent-console/src/features/agents/lib/clipboard.ts`
      - `apps/agent-console/src/features/agents/lib/copyText.ts`
      - `apps/agent-console/src/features/agents/lib/relativeTime.ts`
      - `apps/agent-console/src/features/agents/lib/searchIndex.ts`
      - `apps/agent-console/src/features/agents/lib/exporter.ts`
      - `apps/agent-console/src/features/agents/lib/planApprovalGate.ts`
      - `apps/agent-console/src/features/agents/lib/contextUsage.ts`
      - `apps/agent-console/src/features/agents/lib/localPersistence.ts`
      - `apps/agent-console/src/features/agents/hooks/useStreamFlush.ts`
      - `apps/agent-console/src/features/agents/hooks/useOutsideClick.ts`
      - `apps/agent-console/src/features/agents/components/{PlanApprovalPanel,ComposerToolbar,ContextPopover,PinPopover,ToolMentionChips,ModelPicker,MetadataStrip,MessageActions,MessageEditForm,SearchOverlay,ShortcutOverlay,ContextUsageBar}.tsx`
    - **修改**: `apps/agent-console/src/features/agents/hooks/useChatStream.ts` — 在 `ChatStreamController` 类型与返回对象里新增 `driveBranch(input: { assistantNodeId: string; goal: string; mode: WorkspaceMode }): Promise<void>` 的**签名 + 临时 no-op 实现**（记 `TODO(2.4): wire driveStream`）。
    - **依赖**: —
    - **Requirement / Property / Design**: 约束见 Req 15.3, 15.4；Design §Architecture → "High-level component tree" / "Module layout"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 每个新文件导出最小占位（空对象 / 空函数签名）以让 TypeScript 编译通过。`useChatStream` 的 `driveBranch` 先返回 `Promise.resolve()`，在 Wave 2 Task 3.4 被真正接入 `driveStream`。本任务是后续所有 wave 1+ 任务的结构性前提，避免后续任务各自新建目录引发 race。

- [x] 2. Wave 1 — Pure library functions

  - [x] 2.1 实现 `clipboard.ts` 复制子系统
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/clipboard.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 5.4, 13.8；**Property 7（复制纯度）的基础设施**；Design §New lib modules → `clipboard.ts`、§Error Handling → "Clipboard failure"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `copyText(text): Promise<boolean>`、`supportsCopy(): boolean`、`copyTextExecFallback(text): boolean`。`copyText` 先尝试 `navigator.clipboard.writeText`，失败回退 `copyTextExecFallback`（临时 `<textarea>` + `document.execCommand('copy')` + 移除 DOM）。任一成功返回 `true`；全部失败返回 `false`，绝不 throw（TOTAL）。`supportsCopy` 检测 `typeof navigator !== 'undefined' && (navigator.clipboard || document.execCommand)`。
  
  - [x] 2.2 实现 `copyText.ts` 的 `stripThinkBlocks` 纯函数
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/copyText.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 5.2, 5.7；**Property 7**；Design §New lib modules → `copyText.ts`、§Architecture → "Copy action pipeline"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `stripThinkBlocks(content: string): string`。实现 `content.replace(/<think>[\s\S]*?<\/think>/g, "").trim()`。从 `ChatMessageBubble` 的 v1 私有实现提升到独立 lib 以便独立 PBT。该函数必须是幂等的：`stripThinkBlocks(stripThinkBlocks(c)) === stripThinkBlocks(c)`。

  - [x] 2.3 实现 `relativeTime.ts` 时间格式化
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/relativeTime.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 11.1, 11.2, 11.4；Design §New lib modules → `relativeTime.ts`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `formatRelativeTime(targetMs, nowMs, locale): string`、`formatLocalIso(ms): string`。`formatRelativeTime` 优先使用 `Intl.RelativeTimeFormat`；不可用时手写 `<60s/分/时/天/周/月/年` 的 zh-CN / en 文案回退。`targetMs` 未来时间视为 `0`（避免 NaN）；`nowMs - targetMs` 单位分档：`< 60s → "刚刚"/"just now"`。`formatLocalIso` 用 `new Date(ms).toISOString()`（UI 用 `<time title>` 承载）。

  - [x] 2.4 实现 `searchIndex.ts` 子串搜索
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/searchIndex.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 13.1；Design §New lib modules → `searchIndex.ts`、§Architecture → "Search / Shortcut / Export overlays"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `searchIndex(nodesById, query): SearchHit[]`。`query.trim() === ""` 返回 `[]`。遍历 `Object.values(nodesById)`，对 `node.content.toLowerCase()` 做 `indexOf` 不区分大小写匹配；命中生成 `{ nodeId, role, snippet (±40 字符窗口), matchStart, matchEnd }`。结果排序：role 字典序升序，再按 `created_at` 降序。过滤掉 `role === "system"` 的节点（系统内容不进搜索）。

  - [x] 2.5 实现 `exporter.ts` Markdown/JSON 导出
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/exporter.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 13.3；Design §New lib modules → `exporter.ts`、§Error Handling → "Search / export edge cases"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `exportMarkdown(activePath): string`、`exportJson(activePath): string`、`downloadBlob(contents, filename, mime): void`。`exportMarkdown` 将 `activePath` 序列化为 `### {role}\n\n{content}\n\n---\n\n`；空路径返回 `"# (empty conversation)\n"`。`exportJson` 返回 `JSON.stringify(activePath, null, 2) + "\n"`，空路径返回 `"[]\n"`。`downloadBlob` 创建 `new Blob([contents], { type: mime })`、生成 `URL.createObjectURL`、动态 `<a>` + `.click()` + `revokeObjectURL`（侧效应；不纳入 PBT）。

  - [x] 2.6 实现 `planApprovalGate.ts` 可见性纯谓词
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/planApprovalGate.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 3.1, 3.6, 3.7；**Property 4**；Design §Architecture → "Plan Approval Panel flow"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `planApprovalGate({ activePath, activeStreamNodeId, dismissedPlanNodeIds })`。7 项预条件逐项判定：length > 0 / tail role / tail state / workspace_mode ∈ {plan, markdown_plan} / activeStream === null / tail 未被 dismiss。满足全部 → `{ visible: true, planNode: tail }`；任一不满足 → `{ visible: false, planNode: null }`。TOTAL：对任何 `activePath` 形状（含空数组、undefined metadata）都不得 throw。

  - [x] 2.7 实现 `contextUsage.ts` 用量计算
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/contextUsage.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 13.4, 13.5；Design §New lib modules → `contextUsage.ts`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `computeContextUsage(activePath, turns): { current, limit, ratio }` 与 `readContextWindowLimit(settings): number`。`current = Σ (input_tokens + output_tokens)` 取 `activePath` 最后 `turns` 轮（一轮 = user + assistant 节点对）；缺失字段按 0 累加。`limit` 由调用方通过第二个函数传入；fallback 8192。`ratio = Math.max(0, Math.min(1, current / limit))`。`readContextWindowLimit` 读取 `settings?.defaults?.context_window ?? settings?.models?.[0]?.context_window ?? 8192`（容忍 undefined）。

  - [x] 2.8 实现 `localPersistence.ts` 分区存储
    - **产出（修改）**: `apps/agent-console/src/features/agents/lib/localPersistence.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 12.1–12.6；**Property 11**；Design §Architecture → "Persistence architecture"、§Error Handling → "Persistence failure"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `saveSnapshot(agentId, snapshot): boolean`、`loadSnapshot(agentId): PersistedSnapshot | null`、`clearSnapshot(agentId): void`、`PERSISTED_SCHEMA_VERSION = 1`、`PersistedSnapshot` 类型。storage key = `` `harness.workspace.v2.${agentId}` ``。`saveSnapshot` `try/catch` 包裹 `localStorage.setItem`；失败置 module-local `skipWrites = true` 并 `console.warn`，返回 `false`。`loadSnapshot` 解析 JSON，若 `version !== 1` 返回 `null`（Req 12.4 丢弃）；把 `state === "streaming"` 的节点重写为 `state: "paused"`（Req 12.6 / P11）。

- [x] 3. Wave 2 — Hooks and store extension

  - [x] 3.1 实现 `useStreamFlush` flush 策略 hook
    - **产出（修改）**: `apps/agent-console/src/features/agents/hooks/useStreamFlush.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 2.1, 2.2, 2.3；**Property 2, Property 3**；Design §Architecture → "Streaming flush architecture"、§New hooks → `useStreamFlush`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `useStreamFlush(opts?): StreamFlushApi`。默认策略 `auto`：首次 commit 走 `flushSync(write)`；若过去 4 次 commit 的平均间隔 < 8ms，切到 `raf_window`（rAF 合帧积压 writes，保证相邻 commit ≤ 32ms 且单 delta 可见 ≤ 16ms）。`strategy === "microtask"` 时用 `queueMicrotask(() => flushSync(write))` fallback（JSDOM 环境）。`drain()` 立即 flushSync 未写数据；`useEffect cleanup` 调用 `cancelAnimationFrame` 清理。

  - [x] 3.2 实现 `useOutsideClick` 辅助 hook
    - **产出（修改）**: `apps/agent-console/src/features/agents/hooks/useOutsideClick.ts`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 6.1（支持所有 popover 收起）；Design §New hooks → `useOutsideClick`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 导出 `useOutsideClick<T>(ref, onOutside, enabled = true)`。`useEffect` 监听 `document.mousedown` + `document.touchstart`；若事件 target 不在 `ref.current` 内调用 `onOutside`。`enabled === false` 不绑定监听器。同时监听 `document.keydown` 的 `Escape` 调用 `onOutside`（统一 popover 关闭语义，Req 14.4）。

  - [x] 3.3 扩展 `workspaceStore.ts`（additive + persistence）
    - **产出（修改）**: `apps/agent-console/src/stores/workspaceStore.ts`
    - **依赖**: 2.8
    - **Requirement / Property / Design**: Req 3.5, 12.1–12.6, 15.3；**Property 5, Property 11**；Design §Components → Modified interfaces → `useWorkspaceStore`、§Data Models → `PersistedSnapshot`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build && npm run test -- --run workspaceStore`
    - 追加字段 `dismissedPlanNodeIds: string[]`（默认 `[]`）与两个 action `dismissPlanNode(id)` / `clearDismissedPlanNodes()`；`reset()` 同步清空新字段。通过外层 `subscribe` + 300ms debounce 调用 `saveSnapshot(agentId, partialize(state))`；`agentId` 通过新增 `_agentScope: string | null` + `setAgentScope(agentId)` 注入（页面切换时 rehydrate 使用）。**禁止删改或重命名** `nodesById` / `rootNodeId` / `activeLeafId` / `pinnedNodeIds` / `activeStream` / `draft` / `contextWindowTurns` 现有字段的形状与语义。

  - [x] 3.4 接入 `useChatStream` 的 `driveBranch` + flush + 响应头诊断
    - **产出（修改）**: `apps/agent-console/src/features/agents/hooks/useChatStream.ts`
    - **依赖**: 1.1, 3.1, 3.3
    - **Requirement / Property / Design**: Req 2.1–2.8, 4.4, 10.2, 15.2；**Property 2, Property 3, Property 6**；Design §Architecture → "Branch creation for Edit/Regenerate" / "Streaming flush architecture"、§Error Handling → "SSE streaming diagnostic"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 用 `useStreamFlush().commit(() => store.appendContent(...))` 替换 `dispatchEvent` 内 `delta` / `think_delta` 分支的直接 store 调用；`done` / `error` 前调用 `flush.drain()`。实装 `driveBranch({ assistantNodeId, goal, mode })`：`controllerRef.current` 非空则早退；否则创建 `AbortController`、setActiveStream、调用现有 `driveStream + buildPayload`（**跳过** `planInitialNodes` + `appendNode`）。`runStream` 收到 `response.ok` 后检查 headers：`content-encoding` 命中 gzip/br/deflate 或 `transfer-encoding` 缺失 chunked 且 `content-length` 存在 → `store.updateNode(assistantNodeId, { metadata: { ...m, streaming_diagnostic: "possible_buffering" } })`。不得改动 `streamAgentChatRun` 签名或事件集合（Req 15.2）。

- [x] 4. Wave 3 — Overlay, popover, and action components

  - [x] 4.1 `MessageActions` — Copy / Edit / Regenerate 按钮组
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/MessageActions.tsx`
    - **依赖**: 2.1, 2.2
    - **Requirement / Property / Design**: Req 4.1, 4.8, 5.1, 5.3, 5.4, 5.6, 10.1, 10.4, 10.5, 14.2, 14.3；Design §New components → `MessageActions`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 接口按 design 的 `MessageActionsProps`。内部 `const [justCopied, setJustCopied] = useState(false)` + `useRef<number | null>` 用于 1500ms timer。`onCopy` wrapper：`await props.onCopy()` 成功后 `setJustCopied(true)`，clearTimeout 旧计时器，setTimeout(1500) 复位；失败显示内联 error `<span>`。按钮 className 用 `opacity-0 group-hover:opacity-100 focus-within:opacity-100`；所有 icon-only 按钮带 `aria-label`（i18n：复制/已复制/编辑/重新生成）。`isStreaming === true` 时隐藏 Edit；`isEditing === true` 时隐藏 Edit；`canRegenerate === false` 时隐藏 Regenerate。

  - [x] 4.2 `MessageEditForm` — 编辑态 textarea + 键绑定
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/MessageEditForm.tsx`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 4.2, 4.3, 4.7, 4.9, 8.5, 14.2；Design §New components → `MessageEditForm`、§Error Handling → "Edit validation"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 接口 `{ initialContent, onSave, onCancel }`。内部 `const [value, setValue] = useState(initialContent)` + `const isComposing = useRef(false)`（IME 保护）。键绑定：Enter（非 composition、非 Shift）→ `value.trim() !== "" && onSave(value)`；Shift+Enter 插入换行（原生）；Escape → `onCancel()`。textarea className `bg-white text-slate-900 border border-slate-200 rounded-2xl`（Req 8.5）。「保存并重发」`disabled={value.trim().length === 0}`。建议导出一个辅助纯函数 `editFormShouldSubmit(event, value, isComposing): boolean` 方便 PBT。

  - [x] 4.3 `MetadataStrip` — 元数据一行显示
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/MetadataStrip.tsx`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 7.1–7.8；**Property 8**；Design §New components → `MetadataStrip`、§Architecture → "Metadata Strip contract"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 接口 `{ tail, activeRunId, onOpenRunDetail }`。导出内部辅助纯函数 `formatMetadataField(value, field): string`（`undefined → "—"`、`cost_usd === null || cost_unavailable → "N/A"`、`cost` 保留 4 位、`run_id.slice(0, 8)`）便于 PBT。布局：`<div className="flex items-center gap-3 overflow-x-auto text-xs text-slate-500">`，字段 `In · Out · $cost · TTFB · duration · Run {hash}`。`run_id` 短哈希渲染为 `<button onClick={() => onOpenRunDetail(tail.run_id!)}>`，其余为 `<span>`。容器 **始终可见**（tail 为 null 时 6 个占位符 `—`）。

  - [x] 4.4 `ContextUsageBar` — 上下文用量条
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ContextUsageBar.tsx`
    - **依赖**: 2.7
    - **Requirement / Property / Design**: Req 13.4, 13.5, 14.2；Design §New components → `ContextUsageBar`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 接口 `{ ratio, current, limit }`。`ratio` 在组件内 clamp 到 `[0,1]`。渲染 60×6px 横条 + 左侧 `{formatK(current)}/{formatK(limit)}` 小字；`ratio >= 0.8` 时条填充色从 `bg-slate-400` 切到 `bg-amber-500`，右侧显示 `<AlertTriangle>` + 双语提示"可能需要裁剪上下文 / Context near limit"。`formatK` 是一个本文件内私有纯函数 `(n) => n >= 1000 ? (n/1000).toFixed(1) + 'k' : String(n)`。

  - [x] 4.5 `SearchOverlay` + `ShortcutOverlay` — 全屏帮助/搜索浮层
    - **产出（修改）**:
      - `apps/agent-console/src/features/agents/components/SearchOverlay.tsx`
      - `apps/agent-console/src/features/agents/components/ShortcutOverlay.tsx`
    - **依赖**: 2.4, 3.2
    - **Requirement / Property / Design**: Req 13.1, 13.2, 14.2, 14.4；Design §New components → `SearchOverlay` / `ShortcutOverlay`、§Architecture → "Search / Shortcut / Export overlays"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 两个组件都用 `createPortal` 渲染到 `document.body`，`open === false` 返回 `null`，`open === true` 渲染 `<div role="dialog" className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 pt-[10vh]">`。`SearchOverlay` 自动 focus `<input>`；`onChange → searchIndex(nodesById, q)` 结果列表点击调 `onJumpToNode(nodeId)`。`ShortcutOverlay` 展示静态键盘绑定表（Enter / Shift+Enter / Cmd+K / Esc / ?）。两者都调用 `useOutsideClick(dialogRef, onClose)` 实现外点击与 Esc 关闭。

  - [x] 4.6 `ContextPopover` + `PinPopover` — 上下文与 Pin 列表弹出层
    - **产出（修改）**:
      - `apps/agent-console/src/features/agents/components/ContextPopover.tsx`
      - `apps/agent-console/src/features/agents/components/PinPopover.tsx`
    - **依赖**: 3.2
    - **Requirement / Property / Design**: Req 6.1, 6.2, 6.3, 6.4, 6.7, 6.8, 14.2；Design §New components → 组件表、§Architecture → "Composer toolbar layout"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - `ContextPopover({ value, onChange })`：chip `<button>` 显示 "上下文 {value} / Context {value}"；点击切 open；开启后渲染 `<div className="absolute bottom-full mb-2 w-[320px] rounded-2xl border bg-white p-3 shadow-sm">` 含 `<input type="range" min=2 max=20 value={value}>` + 大号数字标签。`PinPopover({ pinnedNodes, onUnpin })`：chip 上显示计数 `pinnedNodes.length`；列表项 `{role, snippet(40), createdAtRelative}` + 「取消固定」按钮。两者都用 `useOutsideClick(popoverRef, () => setOpen(false))`。

  - [x] 4.7 `ToolMentionChips` + `ModelPicker` — 工具提及与模型切换
    - **产出（修改）**:
      - `apps/agent-console/src/features/agents/components/ToolMentionChips.tsx`
      - `apps/agent-console/src/features/agents/components/ModelPicker.tsx`
    - **依赖**: 3.2
    - **Requirement / Property / Design**: Req 6.1, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 14.2；Design §New components → 组件表。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - `ToolMentionChips({ tools, onInsertMention })`：渲染 `tools.slice(0, 5)` 为 `<button>@{tool.name}</button>`；点击调 `onInsertMention(tool.name)`。`tools.length === 0` 渲染 `<span className="text-xs text-slate-500">无可用工具 / No tools</span>`（Req 6.9）。`ModelPicker({ providers, selectedProviderId, selectedModelId, onModelChange, modelLabelFallback })`：`<button>` 显示当前 `{provider}/{model}` 或 `modelLabelFallback`；点击切 open 显示 dropdown 列表。`providers.length === 0` 时 `disabled`，label 为 "模型设置不可用 / Model settings unavailable" + `modelLabelFallback`（Req 6.10）。dropdown 使用 `useOutsideClick`。

  - [x] 4.8 `PlanApprovalPanel` — Plan 审批浮层
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/PlanApprovalPanel.tsx`
    - **依赖**: 2.6
    - **Requirement / Property / Design**: Req 3.1–3.9, 14.2, 14.3, 14.4；**Property 4, Property 5**；Design §New components → `PlanApprovalPanel`、§Architecture → "Plan Approval Panel flow"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 接口 `{ planNode, isSubmitting, onApprove, onEdit, onDiscard, onClose }`。容器 `<section className="rounded-2xl border border-slate-200 bg-white p-3 shadow-sm">`；4 按钮顺序 批准并执行（primary） / 修改规划（secondary） / 丢弃（ghost） / 关闭 X（右上角 icon-only, `aria-label` 双语）。`isSubmitting === true` 时 4 个按钮 disable。所有文案走 `useI18n().text(zh, en)`。本组件**不**自己判断可见性 — 由父 `ChatSurface` 调用 `planApprovalGate` 决定是否挂载。

- [x] 5. Wave 4 — Composite component changes

  - [x] 5.1 `ComposerToolbar` — 聚合 popover / 用量条 / 导出 / Clear
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ComposerToolbar.tsx`
    - **依赖**: 4.4, 4.6, 4.7
    - **Requirement / Property / Design**: Req 6.1, 6.7, 13.3, 13.4, 12.5, 14.2；Design §New components → `ComposerToolbar`、§Architecture → "Composer toolbar layout"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 按 `ComposerToolbarProps` 组装 `ContextPopover` / `PinPopover` / `ToolMentionChips` / `ModelPicker` / `ContextUsageBar` / Export 下拉（复用 `ShortcutOverlay` 的 `useOutsideClick` 模式；两项 Markdown / JSON）/ Clear `<button>`（触发 `window.confirm` + `onClearConversation`）。水平高度上限通过 `h-auto min-h-[40px] max-h-[56px]` 限制；flex 容器允许 overflow 到第二行但保持整体 ≤ 56px；窄屏下开启 `overflow-x-auto`。

  - [x] 5.2 `ChatMessageBubble` 改 — 白底黑字 + MessageActions + 时间戳 + 诊断
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatMessageBubble.tsx`
    - **依赖**: 2.2, 2.3, 4.1, 4.2
    - **Requirement / Property / Design**: Req 2.8, 4.1, 4.2, 5.1, 5.5, 7 (间接), 8.1–8.7, 10.1, 11.1, 11.2, 11.3；**Property 2 (可见), Property 7, Property 9**；Design §Components → "修改文件" 表 / §New components → `MessageActions` / `MessageEditForm`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - user 分支 className 改为 `bg-white border border-slate-200 text-slate-900 rounded-2xl`（Req 8.1）；max-width 用 `max-w-[75%]`（Req 8.4）；assistant 分支保持 `bg-slate-50 text-slate-800`（Req 8.6 / P9）。加 `group` class 以触发 hover 显示 `MessageActions`。新增 props `editingNodeId`、`onStartEdit`、`onCancelEdit`、`onSaveEdit`、`onCopy`、`onRegenerate`、`canRegenerate`、`isStreaming`。当 `editingNodeId === node.id && role === "user"` 时渲染 `<MessageEditForm>`。气泡外下方渲染 `<time title={formatLocalIso(created)}>{formatRelativeTime(created, Date.now(), locale)}</time>`（Req 11）。`metadata.streaming_diagnostic === "possible_buffering"` 追加 `<p className="mt-2 text-[11px] text-amber-600">` 双语提示（Req 2.8）。删除 bubble 内旧版 `stripThinkBlocks` 局部实现，改 `import { stripThinkBlocks } from "../lib/copyText"`。

  - [x] 5.3 `ChatErrorBubble` 改 — 复制错误详情
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatErrorBubble.tsx`
    - **依赖**: 2.1, 2.2
    - **Requirement / Property / Design**: Req 13.6, 13.8, 14.2；Design §Components → "修改文件"、§Error Handling → "Clipboard failure"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 新增「复制错误详情 / Copy error details」按钮。定义一个局部纯函数 `formatErrorDetail(node, error, agentId)` 产生多行文本（HTTP status / network message / response preview / agentId / run_id）。点击 → `await copyText(formatErrorDetail(...))` → 成功显示打勾 1500ms、失败内联 error。按钮 `aria-label` 双语。

  - [x] 5.4 `ChatMessageList` 改 — 行宽容器 + 透传编辑/复制 props
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatMessageList.tsx`
    - **依赖**: 5.2, 5.3
    - **Requirement / Property / Design**: Req 1.1, 1.2, 1.3, 8.4；**Property 1**；Design §Architecture → "Layout contract"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - **删除**外层所有 `max-w-3xl` / `max-w-2xl` / `max-w-4xl`。外层滚动容器 `flex-1 min-h-0 overflow-y-auto w-full`；内部内容列 `<div className="mx-auto w-full max-w-[80ch] lg:max-w-[56rem] px-3 sm:px-4 lg:px-6 xl:px-12 py-6">`。新增 props `editingNodeId` / `onStartEdit` / `onCancelEdit` / `onSaveEdit` / `onCopy` / `onRegenerate`，透传到每个 `ChatMessageBubble`；`canRegenerate` 仅对末位 assistant 气泡为 true（state ∈ {done, error, paused}）。

  - [x] 5.5 `ChatComposer` 改 — 全宽外壳 + textareaRef 外露
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatComposer.tsx`
    - **依赖**: 1.1
    - **Requirement / Property / Design**: Req 1.1, 1.6, 4.3（编辑态禁用 composer enter 的协作约束）；**Property 1**；Design §Architecture → "Layout contract" / "Editing state ownership"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - **删除** `max-w-3xl` 等宽度约束。外壳 `w-full`，内层 `<div className="mx-auto w-full max-w-[56rem] px-3 sm:px-4 lg:px-6 xl:px-12">`。使用 `forwardRef<HTMLTextAreaElement, ChatComposerProps>` 暴露 textarea ref 供父组件 focus。新增 prop `isEditLocked: boolean`：为 true 时禁用 Enter 提交（交由 `MessageEditForm` 的 Enter 接管），视觉保持不变（避免对现有布局产生回归）。

- [x] 6. Wave 5 — ChatSurface aggregation

  - [x] 6.1 `ChatSurface` 改 — 聚合 Meta / Plan / Toolbar / 编辑态
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
    - **依赖**: 3.4, 4.3, 4.5, 4.8, 5.1, 5.4, 5.5
    - **Requirement / Property / Design**: Req 1.1, 1.2, 1.4, 1.5, 1.6, 3.1–3.7, 4.4, 4.5, 4.9, 7.1, 9.1–9.5, 10.2；**Property 1, Property 4, Property 5, Property 6, Property 8, Property 10**；Design §Architecture → "High-level component tree" / "Editing state ownership" / "Branch creation for Edit/Regenerate"、§Components → "修改文件"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - **删除**根 `<div>` 上的所有 `max-w-*`，改为 `flex h-full w-full min-h-0 flex-col bg-[#f3f5f7]`。`TopMetaBar` 渲染新增 `<MetadataStrip>` + `<StopButton>`（`activeStream !== null` 时挂载，`onClick={() => stream.pause()}`）。本地 `editingNodeId, setEditingNodeId = useState<string|null>(null)`；定义 `handleStartEdit` / `handleCancelEdit` / `handleSaveEdit`，后者按 design 伪码创建新 user + 新 assistant 节点并调用 `stream.driveBranch`。`handleRegenerate` 同理，父为 prev user。`handleApprovePlan` 调 `stream.driveBranch({ assistantNodeId, goal: planNode.content, mode: "plan" })`。底部 sticky footer 渲染 `planApprovalGate` 返回 visible 时的 `<PlanApprovalPanel>` + `<ChatModeBanner>` + `<ComposerToolbar>` + `<ChatComposer>`（`isEditLocked={editingNodeId !== null}`）。

- [x] 7. Wave 6 — Page integration & runbook doc

  - [x] 7.1 `AgentWorkspacePage` 改 + SSE Runbook 文档
    - **产出**:
      - （修改）`apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`
      - （新增）`docs/runbooks/sse-streaming.md`
    - **依赖**: 2.5, 3.3, 4.5, 6.1
    - **Requirement / Property / Design**: Req 1.1, 2.7, 12.2, 12.5, 13.1–13.3, 14.2, 14.4, 15.5, 15.6, 15.7；Design §Architecture → "AgentWorkspacePage modifications" / "Search / Shortcut / Export overlays"、§Error Handling → "Persistence failure"。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`
    - 页面：**删除** `max-w-*` 约束；`useState(searchOpen/shortcutOpen/exportMenuOpen/planSubmitting)`。`useEffect`：绑定全局 `keydown`（Cmd+K / ? / Escape；`?` 需 target 不在 `<input>` / `<textarea>`）；`agentId` 变化时 `store.setAgentScope(agentId)` + `loadSnapshot(agentId)` 回灌 store（把 `state === "streaming"` 节点重写为 `"paused"`、`activeStream = null`）。渲染 `<SearchOverlay>` + `<ShortcutOverlay>` 到 portal。`onExport("markdown"|"json")` 调用 `exporter` lib + `downloadBlob`。`onClearConversation` 触发 `window.confirm` → `clearSnapshot(agentId)` + `store.reset()`。同时创建 `docs/runbooks/sse-streaming.md`，记录 `X-Accel-Buffering: no` / `Cache-Control: no-cache` / Nginx `proxy_buffering off; gzip off;` / Ingress `nginx.ingress.kubernetes.io/proxy-buffering: "off"` 清单（Req 2.7）。

- [ ]* 8. Wave 7 — Property-based test suite

  - [ ]* 8.1 编写 11 条正确性属性的 fast-check 测试（+4 支撑测试）
    - **产出（新增 15 个文件）**: `apps/agent-console/src/features/agents/__tests__/`
      - `layout.property.test.tsx` — **Property 1**，Requirement 1.1, 1.4, 16.1
      - `streamFlush.monotone.property.test.tsx` — **Property 2**，Requirement 2.1, 2.4, 16.2
      - `streamFlush.interval.property.test.tsx` — **Property 3**，Requirement 2.1–2.3, 16.3
      - `planApprovalGate.property.test.ts` — **Property 4**，Requirement 3.1, 3.6, 3.7, 16.4
      - `storePreservation.property.test.ts` — **Property 5**，Requirement 3.5, 14.4, 16.5
      - `branchPreservation.property.test.ts` — **Property 6**，Requirement 4.4–4.6, 10.2, 10.3, 16.6
      - `stripThinkBlocks.property.test.ts` — **Property 7**，Requirement 5.2, 5.7, 16.7
      - `MetadataStrip.property.test.tsx` — **Property 8**，Requirement 7.1–7.4, 16.8
      - `userBubbleColor.property.test.tsx` — **Property 9**，Requirement 8.1, 8.5–8.7, 16.9
      - `StopButton.property.test.tsx` — **Property 10**，Requirement 9.1, 9.3, 16.10
      - `persistence.property.test.ts` — **Property 11**，Requirement 12.2, 12.4, 12.6, 16.11
      - `editFormShouldSubmit.property.test.ts` — 支撑，Requirement 4.3
      - `searchIndex.property.test.ts` — 支撑，Requirement 13.1
      - `exporter.property.test.ts` — 支撑，Requirement 13.3
      - `contextUsage.property.test.ts` — 支撑，Requirement 13.4
    - **依赖**: 2.1–2.8, 3.1–3.4, 4.1–4.8, 5.1–5.5, 6.1, 7.1
    - **Requirement / Property / Design**: Req 16.1–16.11；**Properties P1–P11**；Design §Testing Strategy → Layer 2 表格。
    - **Acceptance**: `cd apps/agent-console && npm run test -- --run property`
    - 每个文件顶部写注释 `// Feature: agent-workspace-chat-v2-refine, Property N: <text>`。使用 `fast-check@^3.23` 的 `fc.assert(fc.property(...))`，`numRuns: 100`。复用 `@testing-library/react` 做 DOM 断言；DOM 环境用 `vitest` 的 `jsdom`。流式时序测试（P2, P3）用 `vi.useFakeTimers` + 模拟 `performance.now` 推进时间，断言 commit 序列满足 ≤16ms / ≤32ms 预算。P9 / Stop / Layout 类测试通过 `render()` + className 字符串断言实现。

- [x] 9. Wave 8 — Acceptance gate

  - [x] 9.1 Final checkpoint — lint / build / test 全绿 + 手动冒烟
    - **产出**: 无新增/修改代码；仅执行下列命令并对照冒烟清单。
    - **依赖**: 1.1, 2.1–2.8, 3.1–3.4, 4.1–4.8, 5.1–5.5, 6.1, 7.1, 8.1
    - **Requirement / Property / Design**: 全体 Req 1–16 的合并门禁；Properties P1–P11；Design §Testing Strategy → "Acceptance gate"。
    - **Acceptance**:
      - `cd apps/agent-console && npm run lint`
      - `cd apps/agent-console && npm run build`
      - `cd apps/agent-console && npm run test`
      - 上述 3 条退出码均为 0。
    - Ensure all tests pass, ask the user if questions arise. 手动冒烟清单见本文件末尾「自测脚本清单」；6 个场景 a–g 必须全部通过。发现回归时回到对应 wave 修复，而不是在本任务中打补丁。

## Notes

- 本计划严格遵守 Req 15：不新增 runtime 依赖、不改 SSE 契约、`useWorkspaceStore` 字段 additive、TypeScript 严格模式下无新增 `any` / `as any` / `@ts-ignore`。
- 所有带 `*` 的子任务（Wave 7 的 PBT）为可选，默认情况下 MVP 可以先跳过，但强烈建议在合并前至少跑通 P1 / P4 / P7 / P9 / P10（这五条与 UX 回归的耦合最强）。
- Wave 7 测试依赖最终实现，因此位于最末 wave；单个测试文件可按需提前编写，但要保证其依赖的 lib / hook / 组件已在其之前的 wave 完成。
- Wave 5 的 `ChatSurface` 是整个 v2 的集成点；若在该步骤发现 Wave 3 / Wave 4 接口不足以承载需求，回到对应组件补齐而非在 `ChatSurface` 里打补丁。

## Property-to-Task Map

| Property | Invariant (short)                              | Validates Requirements          | Primary implementation tasks | PBT task |
| -------- | ---------------------------------------------- | ------------------------------- | ---------------------------- | -------- |
| P1       | Full-width layout (no `max-w-{2,3,4}xl`)       | 1.1, 1.4, 16.1                  | 5.4, 5.5, 6.1, 7.1           | 8.1      |
| P2       | Streaming content monotonic non-decreasing      | 2.1, 2.4, 16.2                  | 3.1, 3.4, 5.2                | 8.1      |
| P3       | Commit interval ≤ 16/32 ms                     | 2.1, 2.2, 2.3, 16.3             | 3.1, 3.4                     | 8.1      |
| P4       | PlanApprovalPanel precondition                  | 3.1, 3.6, 3.7, 16.4             | 2.6, 4.8, 6.1                | 8.1      |
| P5       | Discard/close/Esc preserves store               | 3.5, 14.4, 16.5                 | 3.3, 4.5, 4.8, 6.1, 7.1      | 8.1      |
| P6       | Edit/Regenerate preserves history               | 4.4, 4.5, 4.6, 10.2, 10.3, 16.6 | 3.4, 6.1                     | 8.1      |
| P7       | Copy purity (`stripThinkBlocks`)                | 5.2, 5.7, 16.7                  | 2.1, 2.2, 4.1, 5.2           | 8.1      |
| P8       | Metadata alignment (Strip ≡ Drawer)                | 7.1–7.4, 16.8                   | 4.3, 6.1                     | 8.1      |
| P9       | User bubble color tokens                        | 8.1, 8.5–8.7, 16.9              | 5.2                          | 8.1      |
| P10      | Stop_Button visibility ⇔ activeStream !== null  | 9.1, 9.3, 16.10                 | 6.1                          | 8.1      |
| P11      | Persistence safety (no streaming on rehydrate)  | 12.2, 12.4, 12.6, 16.11         | 2.8, 3.3, 7.1                | 8.1      |

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.7", "2.8"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["4.1", "4.2", "4.3", "4.4", "4.5", "4.6", "4.7", "4.8"] },
    { "id": 4, "tasks": ["5.1", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 5, "tasks": ["6.1"] },
    { "id": 6, "tasks": ["7.1"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["9.1"] }
  ]
}
```

## 自测脚本清单

### 自动化（PR 合并前必跑）

```bash
cd apps/agent-console && npm run lint
cd apps/agent-console && npm run build
cd apps/agent-console && npm run test
```

三条命令必须全部退出码为 0。`npm run test` 默认会以单次模式运行 vitest（包含 Wave 7 的 PBT，每条属性 ≥ 100 次迭代）。

### 手动冒烟（在 `http://localhost:<port>/agents/default/workspace`）

> 启动方式：另起终端运行 `cd apps/agent-console && npm run dev`（本 plan 不自动启动 dev server）。

| # | 场景                                  | 操作步骤                                                                                               | 预期                                                                                                             |
|---|---------------------------------------|--------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| a | 全屏无右侧空白（1920×1080）           | 把浏览器调到 1920×1080，打开 Workspace。                                                                | Meta Bar / Message List / Composer 三段均占满 ConsoleShell 可用宽度，右侧无纯色空白；气泡行宽不超过 56rem。      |
| b | 模型逐字流式可见                       | 选 `chat` 模式，提交 "写一首关于海的长诗"，观察 assistant 气泡。                                         | 文字逐字 / 逐片段出现，绝不是最后一次性一次性出现；`Streaming · N chars` 小字随内容同步更新。                     |
| c | Plan 审批浮层「批准并执行」           | 选 `markdown_plan` 或 `plan` 模式，提交 "帮我规划一次 1 周 CI 加固"。待 plan 输出 `state=done`。           | Composer 正上方出现 Plan 审批浮层，四个按钮可见；点击「批准并执行」后浮层按钮 disable，开始新的 plan-act 流。     |
| d | user 消息 Edit / Copy                  | hover 任意 user 气泡 → 出现 MessageActions。点击 Edit 改几个字后保存并重发；再点击 Copy 查看剪贴板。    | Edit 会创建兄弟 user + 新 assistant 分支、原气泡依然可切换回；Copy 后图标打勾 1.5s 后恢复，剪贴板含纯文本（无 `<think>`）。 |
| e | 模式切换不清 draft                     | 在 Composer 输入 "test"，随后切换 Workspace mode（chat → markdown_plan）。                                | textarea 内容仍然是 "test"；切回 chat 依然保留。                                                                  |
| f | Cmd+K / ? 浮层                         | 聚焦在页面空白处按 `?`；在 Composer 外按 `Cmd+K`（mac）/ `Ctrl+K`（其他）。按 Esc 关闭。                | `?` 打开 Shortcut Overlay；`Cmd+K` 打开 Search Overlay 并自动 focus 输入框；Esc 关闭后 `nodesById` / `draft` 不受影响。 |
| g | 刷新恢复（streaming → paused）         | 发一条触发流式的消息，在流中途（assistant `state === "streaming"`）刷新浏览器。                        | 刷新后历史对话完整，原 streaming 节点变为 `paused` 态（灰色占位 + Resume 按钮），`activeStream === null`。          |

