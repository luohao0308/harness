# Implementation Plan: agent-workspace-chat-refine

## Overview

将 `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`（约 1245 行）重构为聚焦的聊天主界面。本计划按「骨架 → 纯函数模块 → Hook → 视觉组件 → 组装 → 回归」推进，严格遵循 design 的 Module Layout。每个任务都是可独立 PR 的原子步骤，最终产出通过 `tsc --noEmit` 与 `vite build`。

**参考文档**：

- Requirements: `.kiro/specs/agent-workspace-chat-refine/requirements.md`
- Design: `.kiro/specs/agent-workspace-chat-refine/design.md`

**实现语言**：TypeScript（沿用 `apps/agent-console` 现有工具链：React 18、Vite 6、TypeScript 5.7、Tailwind 3.4、Zustand 5、@tanstack/react-query 5、lucide-react）。

**依赖约束**（来自 Req 10.2）：不引入任何新的 **runtime** 依赖；`fast-check` + `vitest` 属于 devDependencies，仅在任务 16（可选）中讨论采纳。主线任务全部通过类型系统 + 纯函数签名 + 手动断言锁死，不依赖 test runner。

## Tasks

- [x] 1. 建立 `features/agents` 子目录骨架与类型入口
  - **产出**：
    - 新建目录 `apps/agent-console/src/features/agents/components/`
    - 新建目录 `apps/agent-console/src/features/agents/hooks/`
    - 新建目录 `apps/agent-console/src/features/agents/lib/`
    - 新建 `apps/agent-console/src/features/agents/lib/types.ts`：导出 `WorkspaceMode = "chat" | "markdown_plan" | "plan"` 与 `InspectorSection = "metadata" | "artifacts" | "runtime"`
  - **依赖**：无
  - **引用**：Design §Module Layout；Req 10.4、10.6
  - **Acceptance**：`npm run lint`（即 `tsc --noEmit`）通过；目录存在但暂不导出到页面

- [x] 2. `lib/sseErrors.ts`：错误分类与文案（Property 6 实现）
  - **产出**：新建 `apps/agent-console/src/features/agents/lib/sseErrors.ts`
    - 导出 `SseErrorKind`、`ConversationErrorMeta`、`SseError` 类（携带 `toMeta()`）
    - 纯函数 `classifyHttpStatus(status: number): SseErrorKind`（401/403→auth、404→not_found、>=500→server、其他非 2xx→http）
    - 纯函数 `classifyFetchError(err: unknown): SseErrorKind`（TypeError/NetworkError/AbortError watchdog→network；其他→server）
    - 纯函数 `isSseContentType(value: string | null): boolean`（大小写不敏感子串匹配 `text/event-stream`）
    - 异步函数 `readBodyPreview(res: Response, maxBytes = 256): Promise<string>`（字节级截断，保证 `<= 256 bytes`）
    - `formatErrorMessage(error, text, context): { title; description }` 与常量 `ERROR_COPY_KEYS`
  - **依赖**：任务 1
  - **引用**：Req 4.1–4.4, 11.3, P3；Property 6；Design §Error Handling、§sseErrors.ts
  - **Acceptance**：`tsc --noEmit` 通过；所有导出均为纯函数或类，不依赖 React

- [x] 3. `lib/markdown.ts`：零依赖 Markdown 子集（Property 1 实现）
  - **产出**：新建 `apps/agent-console/src/features/agents/lib/markdown.ts`
    - `tokenizeMarkdown(source: string): MdToken[]` — 支持 fenced code、headings h1–h6、blockquote、有序/无序列表、paragraph、inline code、link、硬换行
    - `renderMarkdown(source: string): JSX.Element` — 调用 `tokenizeMarkdown` 并渲染为 React 元素；不使用 `dangerouslySetInnerHTML`
    - 常量 `SAFE_URL_PROTOCOLS = ["http:", "https:", "mailto:"]`；不安全链接降级为纯文本
    - 内部辅助 `tokenizeInline`，禁止回溯型正则
  - **依赖**：任务 1
  - **引用**：Req 1.6, 10.2, 10.6；Property 1；Design §Markdown Rendering
  - **Acceptance**：`tsc --noEmit` 通过；对任意输入函数必须 total（不抛异常）；外链以 `target="_blank" rel="noopener noreferrer"` 输出

- [x] 4. `lib/scroll.ts`：自动滚动阈值纯函数（Property 2 实现）
  - **产出**：新建 `apps/agent-console/src/features/agents/lib/scroll.ts`
    - 导出 `shouldAutoScroll(state: { scrollTop: number; clientHeight: number; scrollHeight: number }): boolean`
    - 实现语义：`scrollHeight - scrollTop - clientHeight <= 50`
  - **依赖**：任务 1
  - **引用**：Req 1.8, 1.10；Property 2；Design §ChatSurface
  - **Acceptance**：`tsc --noEmit` 通过；纯函数无副作用

- [x] 5. `lib/examplePrompts.ts` 与 `lib/activePathQueries.ts`（Property 7 实现）
  - **产出**：
    - 新建 `apps/agent-console/src/features/agents/lib/examplePrompts.ts`：`EXAMPLE_PROMPTS` 常量（3–5 条 `{id, zh, en}`）
    - 新建 `apps/agent-console/src/features/agents/lib/activePathQueries.ts`：
      - `findPrevUser(activePath: ConversationNode[], targetNodeId: string): ConversationNode | undefined`
      - `canResume(activePath: ConversationNode[]): boolean`（存在 `state="paused"` 且 `run_id` 非空的 assistant）
      - `shouldShowRunSummary(node: ConversationNode): boolean`（assistant + done + run_id 非空）
  - **依赖**：任务 1；读取 `workspaceStore` 中的 `ConversationNode` 类型
  - **引用**：Req 4.5, 4.6, 5.3, 5.5, 7.5, 8.2；Property 7；Design §useChatStream、§ChatRunSummary
  - **Acceptance**：`tsc --noEmit` 通过；所有查询函数为纯函数

- [x] 6. `workspaceStore` 加入 `ConversationErrorMeta`（additive）
  - **产出**：修改 `apps/agent-console/src/stores/workspaceStore.ts`
    - `ConversationNode.metadata` 新增可选字段 `error?: ConversationErrorMeta`
    - 使用 `import type { ConversationErrorMeta } from "../features/agents/lib/sseErrors"`（仅类型导入，避免循环依赖）
    - 不删除、不重命名、不改变任何已有字段
  - **依赖**：任务 2
  - **引用**：Req 10.4；Design §Data Structures
  - **Acceptance**：`tsc --noEmit` 通过；现有消费者无需改动即可继续运行

- [x] 7. `features/tasks/api.ts`：导出 `parseChatSseFrame`（最小改动）
  - **产出**：修改 `apps/agent-console/src/features/tasks/api.ts`
    - 将内部 `parseChatSseFrame` 改为 `export function parseChatSseFrame`
    - 不改 `streamAgentChatRun` 的签名与请求体字段；不改 `AgentChatStreamEvent` 联合
  - **依赖**：无
  - **引用**：Req 10.3；Design §Wrapping streamAgentChatRun
  - **Acceptance**：`tsc --noEmit` 通过；`streamAgentChatRun` 外部调用点零变更

- [x] 8. `lib/chatEventReducer.ts`：纯状态机 reducer（Property 5 + Property 4 实现）
  - **产出**：新建 `apps/agent-console/src/features/agents/lib/chatEventReducer.ts`
    - `planInitialNodes(draft: string, mode: WorkspaceMode): [UserNodePatch, AssistantNodePatch]`（Property 4 主体）
    - `applyChatEvents(init: AssistantNodeSnapshot, events: ChatReducerEvent[]): AssistantNodeSnapshot`，其中 `ChatReducerEvent = AgentChatStreamEvent | { type: "abort" } | { type: "http_error" | "network_error" | "non_sse" | "stream_closed"; meta: ConversationErrorMeta }`
    - 保证：终态 `state ∈ {streaming, done, paused, error}`；进入终态后后续事件不得回退；error 优先于 abort（Req 4.8）
    - `mergeErrorMeta(existing, next): ConversationNode["metadata"]`
  - **依赖**：任务 2、任务 6
  - **引用**：Req 3.1, 3.3–3.6, 3.8, 4.7, 4.8, 4.9, 11.2；Property 4、Property 5；Design §SSE Parsing、§Error routing
  - **Acceptance**：`tsc --noEmit` 通过；reducer 对任意事件序列 total；类型签名强制 `state` 的终态枚举

- [x] 9. `hooks/useChatStream.ts`：SSE 驱动 Hook（状态机宿主）
  - **产出**：新建 `apps/agent-console/src/features/agents/hooks/useChatStream.ts`
    - 导出 `useChatStream(args: UseChatStreamArgs): ChatStreamController`
    - Controller 暴露 `isStreaming`、`start`、`pause`、`resume`、`retry`
  - **子步骤（全部落在同一任务中）**：
    - 9.1 Pre-flight：调用 `planInitialNodes`，用 `useWorkspaceStore.appendNode` 原子创建 user/assistant 两节点；挂 `AbortController` 并写入 `setActiveStream`
    - 9.2 Watchdog：10s `setTimeout` 超时 → `controller.abort(new DOMException("connection timeout", "AbortError"))`；首个 delta/think_delta/run_created 清除
    - 9.3 Request 包装：本地 `runStream(...)`，非 2xx → `throw new SseError(classifyHttpStatus(status), ...)`；Content-Type 非 SSE → `throw new SseError("non_sse", body_preview)`
    - 9.4 Event dispatch：复用 `parseChatSseFrame`，按 design §SSE Parsing 的分支分别 `updateNode`/`appendContent`/`appendArtifact`；`done` 触发 `sawDone=true`；reader 结束未见 done → `throw new SseError("stream_closed")`
    - 9.5 Error routing：单一 `catch` 块；若 `controllerRef.current !== abort` 立即 return；否则写 `state="error"` + `metadata.error`；仅当 `abort.signal.aborted` 且未发生 `SseError(non stream_closed)` 时降级为 `paused`
    - 9.6 `pause()`：调用 `controller.abort()`，终态由 catch 分支决定（Req 4.8）
    - 9.7 `resume(pausedNodeId)`：校验 `paused.run_id`，缺失则写 error；用 `findPrevUser` 拿 goal，调用 `driveStream` 并附带 `continue_from_node_id` / `partial_assistant_content`
    - 9.8 `retry(errorNodeId)`：用 `findPrevUser` 拿上一条 user content，调用 `start` 开新 user/assistant 对
  - **依赖**：任务 2、5、7、8；现有 `workspaceStore`、`streamEvents.ts`
  - **引用**：Req 3, Req 4, Req 5, P2, P3；Design §useChatStream Hook 完整章节
  - **Acceptance**：`tsc --noEmit` 通过；Hook 与 React 状态/Zustand 正确耦合；无 `any`/`ts-ignore`

- [x] 10. `components/ChatComposer.tsx`：输入框与键位状态机（Property 3 实现）
  - **产出**：新建 `apps/agent-console/src/features/agents/components/ChatComposer.tsx`
    - 导出纯函数 `composerShouldSubmit(event, draft, isStreaming): boolean`（Property 3 主体）
    - 组件：多行 `<textarea>` + 主发送按钮 + 模式选择 + Pause/Resume 次级按钮 + 提示文案「Enter 发送 · Shift+Enter 换行」（i18n）
    - 替换 `AgentWorkspacePage.tsx` 内原 Composer（含 `handleComposerKeyDown`、`MentionTray`）中的键位处理
    - 提交后 `setDraft("")` 并 `textareaRef.current?.focus()`
  - **依赖**：任务 1、任务 5（`canResume`）
  - **引用**：Req 2.1–2.8, 5.1, 5.3, 5.6, 9.3–9.5, P6；Property 3；Design §Composer Keyboard
  - **Acceptance**：`tsc --noEmit` 通过；组件可在 Storybook 之外被 `ChatSurface` 引用；纯函数 `composerShouldSubmit` 可独立被测试

- [x] 11. `components/ChatMessageBubble.tsx` / `ChatErrorBubble.tsx` / `ChatRunSummary.tsx` / `ChatWelcomeState.tsx`
  - **产出**：
    - `components/ChatMessageBubble.tsx`：user/assistant/tool 气泡；调用 `renderMarkdown(node.content)`；折叠思考块；tool_call chip 列表；artifact chip 列表；streaming 时加 `role="status"` `aria-live="polite"` 与闪烁光标（替换旧 `AgentWorkspacePage` 内对应 inline 渲染）
    - `components/ChatErrorBubble.tsx`：`role="alert"`；调用 `formatErrorMessage`；展示 `body_preview` 为 `<pre max-h-24 overflow-auto>`；附带 Retry 按钮
    - `components/ChatRunSummary.tsx`：assistant+done+run_id 时渲染；短哈希 + 状态徽标 + `<Link to={"/runs/" + runId}>`
    - `components/ChatWelcomeState.tsx`：展示 agentName + modelLabel + ≤3 行介绍 + 3–5 条 `EXAMPLE_PROMPTS`；点击后 `onPickPrompt(prompt)`
  - **依赖**：任务 3（markdown）、任务 5（examplePrompts）、任务 2（`formatErrorMessage`）
  - **引用**：Req 1.4–1.6, 3.2, 3.4, 3.7, 4.1–4.5, 7.5, 8.1–8.3, 9.1, 9.5；Design §Module Layout 四个组件
  - **Acceptance**：`tsc --noEmit` 通过；四个组件均为 stateless；无 `dangerouslySetInnerHTML`

- [x] 12. `components/ChatMessageList.tsx` 与 `components/ChatModeBanner.tsx`
  - **产出**：
    - `components/ChatMessageList.tsx`：按 `activePath` 渲染；空 → `ChatWelcomeState`；否则映射到 bubble/error bubble；尾部挂 `ChatRunSummary`；使用 `shouldAutoScroll` 控制 `scrollIntoView`
    - `components/ChatModeBanner.tsx`：`workspaceMode !== "chat"` 时展示提示条，提供「切回 Chat」与「创建 Run」入口（Req 6.3）
  - **依赖**：任务 4（scroll）、任务 11
  - **引用**：Req 1.1, 1.8, 1.10, 6.3；Design §ChatMessageList、§Mode Handling
  - **Acceptance**：`tsc --noEmit` 通过；滚动逻辑通过 `useEffect` + `scrollAnchorRef` 实现，不直接操纵 DOM 全局

- [x] 13. `components/InspectorDrawer.tsx`：抽屉（仅链接，不渲染全量表格）
  - **产出**：新建 `apps/agent-console/src/features/agents/components/InspectorDrawer.tsx`
    - 三个 section：Metadata（SmallMetric 六宫格）、Artifacts（`all.slice(-10)`，支持选中预览）、Runtime（pending approvals banner + 跳转到 `/runs/:runId#approvals|#plan|#model-calls|#tool-runtime` / `/observability` / `/evals` 的 LinkGroup）
    - `role="dialog"` `aria-modal="true"`；Esc 关闭；焦点回溯到触发按钮
    - 显式**不**渲染 Approve/Reject/Modify 控件、Plan DAG、Model Calls 表格、Tool Call Runtime 表格、Save as Eval Case
    - 替换 `AgentWorkspacePage.tsx` 内旧 `WorkspaceInspectorDrawer`
  - **依赖**：任务 1
  - **引用**：Req 7.1–7.8, 9.3, P4；Design §Inspector Drawer
  - **Acceptance**：`tsc --noEmit` 通过；文件内不存在字符串字面量 "Approve"/"Save as Eval Case"/"Plan DAG"（除负向注释外）

- [x] 14. `components/ChatSurface.tsx`：聚合聊天主视口（三行布局）
  - **产出**：新建 `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
    - 三行 Sticky 布局：`<header>TopMetaBar</header>`（固定顶部，含 `agentName` / `modelLabel` / `workspaceMode` 徽标 / `Streaming` 徽标 / 跳 Run Detail 主入口）+ `<section>ChatMessageList</section>`（`min-h-0 overflow-y-auto`）+ `<footer>ChatModeBanner? + ChatComposer</footer>`
    - 在 `activeRunId != null` 且最末 assistant `state=done` 时挂 `ChatRunSummary`
    - 暴露 `onOpenInspector` 供 TopMetaBar 内三个图标按钮调用
  - **依赖**：任务 10、11、12
  - **引用**：Req 1.1–1.3, 1.7, 1.9, 7.5, 7.6；Design §Architecture、§ChatSurface
  - **Acceptance**：`tsc --noEmit` 通过；中部滚动区使用 `flex-1 min-h-0`；TopMetaBar 与 Composer 均使用 Tailwind sticky 定位

- [x] 15. 组装与清理：重写 `AgentWorkspacePage.tsx` ≤ 120 行
  - **产出**：重写 `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`
    - 仅保留：`useParams` 取 `agentId`；`useQuery(getAgent/getModelSettings/getToolRegistry)`（settings/tools 非阻塞，Req 10.5）；`useState<WorkspaceMode>("chat")`；`useState<InspectorSection | null>(null)`；`useState<activeRunId>`；`useChatStream(...)`
    - 返回 `<ConsoleShell><ChatSurface .../></ConsoleShell>` 与 `<InspectorDrawer .../>`
    - 删除旧的 inline 组件：`Explorer`、`WorkspaceInspectorDrawer`、`MetricsPanel`、`ToolRuntimePanel`、`ArtifactsPanel`、`WelcomeMessage`、`MentionTray`、`handleComposerKeyDown` 等
    - 不新增 `any` 或 `ts-ignore`；不更改 `apps/agent-console/src/app/routes.tsx`
  - **依赖**：任务 9、13、14
  - **引用**：Req 1.1, 6.1, 6.4, 6.5, 7, 8.4–8.6, 9, 10.1, 10.5, 10.6, P4, P5；Design §AgentWorkspacePage
  - **Acceptance**：
    - `cd apps/agent-console && npm run lint` 通过
    - `cd apps/agent-console && npm run build` 通过
    - `AgentWorkspacePage.tsx` 行数 ≤ 120
    - 手动跑 `npm run dev` 并在 `/agents/default/workspace` 验证：
      1. 纯 Enter 发送（无 Shift/无 Cmd）；Shift+Enter 换行
      2. 停掉后端时错误气泡可见且「重试」按钮可用
      3. 在 `chat ↔ markdown_plan ↔ plan` 间切换，`Active_Path` 与 `draft` 均保留

- [x] 16. 可选：采纳 vitest + fast-check 并为 Property 1–8 写 property-based tests
  - **产出**：
    - 修改 `apps/agent-console/package.json`：在 `devDependencies` 中加入 `vitest`、`@vitest/ui`（可选）、`fast-check`；`scripts.test` 指向 `vitest --run`；不引入任何新的 runtime 依赖（Req 10.2）
    - 新建 `apps/agent-console/vitest.config.ts`（最小配置，复用 Vite）
    - 新建 `apps/agent-console/src/features/agents/__tests__/` 下：
      - `markdown.property.test.ts` — Property 1（实现已在任务 3）
      - `shouldAutoScroll.property.test.ts` — Property 2（实现已在任务 4）
      - `composerShouldSubmit.property.test.ts` — Property 3（实现已在任务 10）
      - `planInitialNodes.property.test.ts` — Property 4（实现已在任务 8）
      - `applyChatEvents.property.test.ts` — Property 5（实现已在任务 8）
      - `sseErrors.property.test.ts` — Property 6（实现已在任务 2）
      - `activePathQueries.property.test.ts` — Property 7（实现已在任务 5）
      - `modeSwitch.property.test.ts` — Property 8（实现已在任务 15 的组装行为）
    - 每个测试文件首行注释 `// Feature: agent-workspace-chat-refine, Property {N}: {title}`；运行迭代数 ≥ 100
  - **依赖**：任务 2、3、4、5、8、10、15
  - **引用**：Req 10.2（dev-only 允许）；Design §Testing Strategy、§Correctness Properties
  - **Acceptance**：`cd apps/agent-console && npx vitest run` 全部通过；`npm run lint` 与 `npm run build` 不受影响；若不采纳，本任务可整体跳过

## Property-to-Task Mapping（方便追溯）

| Property | 实现任务 | 测试任务（可选） |
| --- | --- | --- |
| P1 Markdown safety & text preservation | 任务 3 | 任务 16 `markdown.property.test.ts` |
| P2 Auto-scroll threshold | 任务 4 | 任务 16 `shouldAutoScroll.property.test.ts` |
| P3 Composer submit truth table | 任务 10 | 任务 16 `composerShouldSubmit.property.test.ts` |
| P4 Initial node structure | 任务 8（`planInitialNodes`） | 任务 16 `planInitialNodes.property.test.ts` |
| P5 Chat event reducer invariants | 任务 8（`applyChatEvents`） | 任务 16 `applyChatEvents.property.test.ts` |
| P6 SSE error classification | 任务 2 | 任务 16 `sseErrors.property.test.ts` |
| P7 Active-path queries | 任务 5 | 任务 16 `activePathQueries.property.test.ts` |
| P8 Mode-switch snapshot preservation | 任务 15（组装时保持不重置） | 任务 16 `modeSwitch.property.test.ts` |

## Notes

- 每个任务自身必须通过 `tsc --noEmit`，不允许留下「破坏构建」的半成品——即使上层组装尚未完成，新文件也只是暂时未被引用。
- 不在任务里描述测试用例细节；property 的具体生成器与断言在任务 16 实现阶段再设计。
- 严格遵循 design 的文件命名与路径。不允许新增 design 未列出的模块。
- 所有用户可见文案必须走 `useI18n().text(zh, en)`，错误文案走 `ERROR_COPY_KEYS`（Req 9.1, 9.2）。
- `streamAgentChatRun` 的签名与请求体、`AgentChatStreamEvent` 集合保持不变；任务 7 仅是 `parseChatSseFrame` 加 `export`。

## 自测脚本清单

进入前端工作区并执行：

```
cd apps/agent-console
npm run lint      # tsc --noEmit
npm run build     # tsc --noEmit && vite build
```

可选（仅当任务 16 已完成）：

```
cd apps/agent-console
npx vitest run
```

手动冒烟（在 `/agents/default/workspace`）：

1. **Enter 发送**：在输入框输入一段文本，直接按 `Enter` → 应立即触发流式请求并创建用户 + 助手气泡；按 `Shift+Enter` → 只换行不提交。
2. **SSE 错误可视化**：停掉后端或改错 `VITE_API_BASE_URL`，触发一次发送 → 应见错误气泡包含可读原因（「无法连接 Harness 后端」或 HTTP 状态码）与「重试」按钮。
3. **模式切换不清 draft**：在输入框输入文本但不发送，在 `chat ↔ markdown_plan ↔ plan` 之间来回切换 → 输入框内容与已有对话历史均保持不变。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1", "7"] },
    { "id": 1, "tasks": ["2", "3", "4", "5"] },
    { "id": 2, "tasks": ["6", "8"] },
    { "id": 3, "tasks": ["9", "10", "11", "13"] },
    { "id": 4, "tasks": ["12"] },
    { "id": 5, "tasks": ["14"] },
    { "id": 6, "tasks": ["15"] },
    { "id": 7, "tasks": ["16"] }
  ]
}
```
