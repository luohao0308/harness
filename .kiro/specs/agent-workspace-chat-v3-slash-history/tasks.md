# Implementation Plan: agent-workspace-chat-v3-slash-history

> 基于 design.md 落地 v3 的 6 条反馈。语言与约束沿用 v2：TypeScript 严格模式、**不新增 runtime 依赖**、**不改 SSE 契约**、`useWorkspaceStore` additive。所有改动限定在 `apps/agent-console/`。

## Tasks

- [x] 1. Wave 0 — 纯函数 lib（可独立单测）

  - [x] 1.1 `slashCommands.ts` — 命令清单与解析器
    - **产出（新增）**: `apps/agent-console/src/features/agents/lib/slashCommands.ts`
    - **Requirement / Property**: Req 5.1–5.11；P12 / P13 / P14
    - 导出 `SlashCommandName / SlashCommand / SlashParseResult / SLASH_COMMANDS / parseSlashCommand / filterCommandsByPrefix / replaceSlashPrefix`。9 条命令 per design table。`parseSlashCommand` TOTAL、纯函数，对任意字符串返回 `{ kind: "none" | "matching" | "confirmed" }`；`confirmed` 的 `restDraft` 去除 `/command` 前缀。`filterCommandsByPrefix` 大小写不敏感 + 别名前缀匹配。`replaceSlashPrefix(draft, name)` 用 `/{name} ` 替换第一段 `/xxx`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 1.2 `conversationHistory.ts` — 历史对话的纯函数 + 持久化
    - **产出（新增）**: `apps/agent-console/src/features/agents/lib/conversationHistory.ts`
    - **Requirement / Property**: Req 4.*；P15 / P16 / P17
    - 导出 `ConversationSummary / ConversationsSnapshot / CONVERSATIONS_SCHEMA_VERSION / sortConversationsByUpdatedAt / computeConversationTitle / genesisConversation / legacyMigration / saveConversationsSnapshot / readConversationsSnapshot / clearConversationsSnapshot`。storage key `harness.workspace.v3.<agentId>.conversations`；write 失败同 v2 模块级 `skipWrites`。`sortConversationsByUpdatedAt` 稳定倒序（对相等时间保留 input order）。`legacyMigration(v2Snapshot, now, idFactory)` 纯函数，返回单元素数组。`genesisConversation(now, idFactory)` 返回空对话。`computeConversationTitle(nodesById, fallback)` 取首条 user 消息 `content.trim().slice(0, 40)` 或 fallback。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 1.3 `composerAutogrow.ts` + `autoScrollFollow.ts` — UI 支撑纯函数
    - **产出（新增）**:
      - `apps/agent-console/src/features/agents/lib/composerAutogrow.ts`
      - `apps/agent-console/src/features/agents/lib/autoScrollFollow.ts`
    - **Requirement / Property**: Req 1.*, Req 2.*；P18 / P19
    - `composerAutogrow.ts` 导出 `MIN_COMPOSER_HEIGHT = 40 / MAX_COMPOSER_HEIGHT = 200 / clampAutogrowHeight(scrollHeight): number`。对 NaN / 负数 / undefined 回退 MIN。
    - `autoScrollFollow.ts` 导出 `computeFollowDecision({ autoFollow, prevContentSum, nextContentSum }): { shouldScroll: boolean }`；另导出 `contentSum(activePath): number`。`shouldScroll === autoFollow && nextContentSum > prevContentSum`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

- [x] 2. Wave 1 — store additive 扩展

  - [x] 2.1 `workspaceStore.ts` — 追加 conversations / currentConversationId / actions / 新 persistence
    - **产出（修改）**: `apps/agent-console/src/stores/workspaceStore.ts`
    - **依赖**: 1.2
    - **Requirement / Property**: Req 4.2–4.11, Req 8.3；P16
    - 追加字段 `conversations / currentConversationId / historyPanelCollapsed`，初始值：`[genesisConversation(now, fixedId)]` / `<该条目 id>` / `false`；追加 actions `newConversation / setCurrentConversation / deleteConversation / renameConversation / setHistoryPanelCollapsed / hydrateFromConversations`。
    - `setCurrentConversation(id)`：先把当前 store runtime 快照写回当前 `conversations[i]`（`updated_at` 置 now）；再从目标 conversation 读取 `nodesById/rootNodeId/activeLeafId/pinnedNodeIds/dismissedPlanNodeIds/draft/contextWindowTurns` 覆盖到 store；更新 `currentConversationId`。
    - `deleteConversation(id)`：filter 掉；若删除的是 current → 切到 `sortConversationsByUpdatedAt(remaining)[0]`；若 remaining 为空 → 新建 genesis 并切换。
    - `newConversation()`：把当前 store runtime 写回；追加一个 genesis；切换 current；返回新 id。
    - `hydrateFromConversations(snapshot)`：在挂载时一次性回填 store，不触发写回循环（通过在 hydrate 期间 set `_agentScope = null` 再恢复的方式避免递归，或直接用 `set` 批量赋值且 subscribe 的 debounce 自然合并）。
    - **Persistence 改写**：subscribe 回调内把 `state` 的运行时快照合并到 `state.conversations` 中的 current 条目，再调用 `saveConversationsSnapshot(agentId, { version: 2, conversations, currentConversationId })`。原 `saveSnapshot` 调用移除（v2 旧 key 不再写入）。
    - `reset()` 不再 reset conversations 列表，只重置 runtime 字段（保留 v1 / v2 语义）。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build && npm run test -- --run`

- [x] 3. Wave 2 — 新组件

  - [x] 3.1 `SlashCommandMenu.tsx`
    - **产出（新增）**: `apps/agent-console/src/features/agents/components/SlashCommandMenu.tsx`
    - **依赖**: 1.1
    - **Requirement / Property**: Req 5.*、Req 7.3
    - 纯展示，props `{ open, candidates, activeIndex, onHover, onSelect }`。`role="listbox"`、每项 `role="option"` + `aria-selected`；双语描述；空态提示 "没有匹配的命令 / No matching command"。容器 `absolute bottom-full mb-2 w-[360px] rounded-2xl border bg-white shadow-xl p-1`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 3.2 `ConversationHistoryPanel.tsx`
    - **产出（新增）**: `apps/agent-console/src/features/agents/components/ConversationHistoryPanel.tsx`
    - **依赖**: 1.2
    - **Requirement / Property**: Req 4.1–4.7, Req 7.*
    - Props 见 design。`collapsed` 时容器 `w-0 overflow-hidden border-0`；展开时 `w-[260px] shrink-0 border-r border-slate-200 bg-white`。header 行：新建按钮 + 折叠按钮。list 用 `sortConversationsByUpdatedAt`，每项 `title` 截断 + 相对时间 + hover 显示 `Trash2` 删除按钮；当前项 `bg-slate-100 ring-1 ring-slate-300`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 3.3 `JumpToLatestButton.tsx` + `InspectorMenu.tsx`
    - **产出（新增）**:
      - `apps/agent-console/src/features/agents/components/JumpToLatestButton.tsx`
      - `apps/agent-console/src/features/agents/components/InspectorMenu.tsx`
    - **依赖**: —
    - **Requirement / Property**: Req 2.4, 2.5, 6.2, 7.2, 7.4
    - `JumpToLatestButton`：icon-only `ChevronDown` + 双语 aria-label；props `{ onClick }`。
    - `InspectorMenu`：单按钮 + 下拉三行（Metadata/Artifacts/Runtime）；`useOutsideClick` + Escape 关闭；双语 label。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

- [x] 4. Wave 3 — 现有组件修改

  - [x] 4.1 `ChatComposer.tsx` — autogrow + slash 拦截 + 移除 mode radio
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatComposer.tsx`
    - **依赖**: 1.1, 1.3, 3.1
    - **Requirement / Property**: Req 1.*, Req 5.*, Req 6.7, Req 7.2；P18
    - `useLayoutEffect([draft])` 调用 `autogrowTextarea(ref.current)`：`el.style.height = 'auto'; next = clampAutogrowHeight(el.scrollHeight); el.style.height = next + 'px'; el.style.overflowY = el.scrollHeight > MAX ? 'auto' : 'hidden'`。初始 className 用 `resize-none overflow-hidden` 替代 `min-h-24`。
    - 新 prop `onSlashDispatch?`. 在渲染中内联 `const slashState = parseSlashCommand(draft);` 与本地 state `slashIndex`。当 `slashState.kind === "matching" | "confirmed" (still showing)` 时渲染 `<SlashCommandMenu open candidates activeIndex onHover onSelect />` 在 textarea 上方。
    - `handleKeyDown` 在 slashOpen 时拦截 `ArrowDown/Up/Enter/Escape/Tab`：`Enter` 分派当前高亮 → `onSlashDispatch(cmd, args)`；`Tab` 补全 → `onDraftChange(replaceSlashPrefix(...))`。slash dispatch 内部清空 draft（无 args）或替换 tool 片段。
    - 删除底部的 `<div role="radiogroup">` 整块 UI；保留 `mode / onChangeMode` props 以向后兼容（不渲染 UI）。保留"Enter 发送 · Shift+Enter 换行"提示。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 4.2 `ChatMessageList.tsx` — 自动跟随滚动重做
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatMessageList.tsx`
    - **依赖**: 1.3, 3.3
    - **Requirement / Property**: Req 2.*；P19
    - 新 refs：`scrollContainerRef` + `sentinelRef`；新 state：`autoFollow: boolean = true` + `distanceToBottom: number = 0`。
    - `useEffect(mount, [scrollContainerRef])`：新建 IntersectionObserver(root = scrollContainer, threshold = 0)，观察 sentinel；entry.isIntersecting → 设 `autoFollow = true` + `distanceToBottom = 0`；否则 `autoFollow = false` + `distanceToBottom = scrollHeight - scrollTop - clientHeight`。在 JSDOM / IO 不可用时 fallback：`typeof IntersectionObserver === "undefined" || scrollContainer === null` → 跳过 observer（autoFollow 保持 true）。
    - `useLayoutEffect([contentSum(activePath)])`：`if (autoFollow && scrollContainer) scrollTop = scrollHeight - clientHeight;`
    - render：`<div ref={scrollContainerRef} ...>` 外层；inner 内容列；末尾 `<div ref={sentinelRef} style={{ height: 1 }} />`；当 `!autoFollow && distanceToBottom >= 200` → 悬浮 `<JumpToLatestButton onClick={jumpToBottom} />`（容器上 `relative`）。
    - `jumpToBottom()`：`scrollContainer.scrollTo({ top: scrollHeight, behavior: "smooth" });` + 立即 `setAutoFollow(true)`。
    - 删除 v2 的 `shouldAutoScroll` 依赖（保留 `lib/scroll.ts` 文件不动，以免破坏 `shouldAutoScroll.property.test.ts`）。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 4.3 `ChatSurface.tsx` — metadata 迁移 + Inspector 合并 + slash 回调 + 模式 badge 条件渲染 + 删 ChatModeBanner
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
    - **依赖**: 2.1, 3.3, 4.1, 4.2
    - **Requirement / Property**: Req 3.*, Req 5.*, Req 6.*
    - `TopMetaBar`：删除 `<MetadataStrip>`（以及子组件分配的 Props）、把 `Metadata/Artifacts/Runtime` 三按钮替换为 `<InspectorMenu onOpenInspector={onOpenInspector} />`；`Workspace_Mode` badge 在 `mode === "chat"` 时不渲染。
    - `footer`：在 `<PlanApprovalPanel>` 下、`<ComposerToolbar>` 上插入 `<div className="mx-auto w-full max-w-[56rem] px-3 sm:px-4 lg:px-6 xl:px-12 text-[11px] text-slate-400"><MetadataStrip tail={...} activeRunId={...} onOpenRunDetail={...} /></div>`。
    - 删除 `{workspaceMode !== "chat" && <ChatModeBanner .../>}`。
    - 新 callback：`onOpenSearch / onOpenShortcut / onOpenModelPicker`（从 `AgentWorkspacePage` 注入）；新 slash dispatcher：`handleSlashDispatch(cmd, args)` switch 分派到对应 callback / store action / draft 操作。传给 `<ChatComposer onSlashDispatch={handleSlashDispatch} />`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 4.4 `AgentWorkspacePage.tsx` — 渲染 HistoryPanel + slash 回调 + 迁移
    - **产出（修改）**: `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`
    - **依赖**: 1.2, 2.1, 3.2, 4.3
    - **Requirement / Property**: Req 4.*, Req 5.*, Req 6.*, Req 7.1
    - 布局：`<div className="relative flex h-[calc(100vh-3.5rem)] w-full min-h-0">` 下首先挂 `<ConversationHistoryPanel>`，再 `<ChatSurface>` + `<InspectorDrawer>`。
    - `useEffect([agentId])` 替换 v2 的 `loadSnapshot` 逻辑：
      1. setAgentScope(agentId)
      2. v3 = readConversationsSnapshot(agentId)；若有 → hydrateFromConversations(v3)；记得把所有 streaming 节点重写成 paused。
      3. 若 v3 无，loadSnapshot(agentId)（v2）→ 若有 → `legacyMigration` → hydrateFromConversations({ conversations: [migrated], currentConversationId: migrated.id }) → saveConversationsSnapshot + clearSnapshot(agentId)（v2 key）。
      4. 若都无 → hydrateFromConversations({ conversations: [genesisConversation(now, uuid)], currentConversationId: ... }).
    - 新 state `modelPickerOpen: boolean`（由 `/model` 触发打开），传给 `ChatSurface` 再透传到 `ComposerToolbar` / `ModelPicker`（或：通过 URL fragment / toolbar 自带状态，但本任务用 callback 最直接）。**实现简化**：新增 `modelPickerRequestSeq` 整数，每调用 `onOpenModelPicker` 就 +1；`ModelPicker` 用 `useEffect([seq])` 打开下拉。
    - 新 callbacks `handleNewConversation / handleSelectConversation / handleDeleteConversation / handleToggleHistoryCollapsed`，直接委托 store actions。
    - 更新 `handleClearConversation`：从 v2 的 `clearSnapshot(agentId) + reset()` 改为只 `reset()`（因为 v3 persistence 由 conversations 列表驱动；reset 会导致 store 重置当前 conversation 的 runtime 字段，subscribe 会把这个空状态写回当前 conversation；无需显式删 localStorage key）。
    - 新 `onOpenSearch / onOpenShortcut` 复用现有 `setSearchOpen / setShortcutOpen`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 4.5 `ComposerToolbar.tsx` — ModelPicker open seq 透传
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ComposerToolbar.tsx`
    - **依赖**: 4.4
    - **Requirement / Property**: Req 5.2
    - 新 prop `modelPickerOpenSeq?: number`（additive）；透传到 `<ModelPicker ... modelPickerOpenSeq={modelPickerOpenSeq} />`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

  - [x] 4.6 `ModelPicker.tsx` — 响应 open seq
    - **产出（修改）**: `apps/agent-console/src/features/agents/components/ModelPicker.tsx`
    - **依赖**: 4.5
    - 新 prop `modelPickerOpenSeq?: number`；`useEffect([seq])` 当 seq 变化且大于 0 时 `setOpen(true)`。
    - **Acceptance**: `cd apps/agent-console && npm run lint && npm run build`

- [x] 5. Wave 4 — Property-based tests

  - [x]* 5.1 slash commands 属性测试（P12/P13/P14）
    - **产出（新增）**: `apps/agent-console/src/features/agents/__tests__/slashCommands.property.test.ts`
    - 覆盖 P12 / P13 / P14。
    - **Acceptance**: `cd apps/agent-console && npm run test -- --run`

  - [x]* 5.2 conversation history 属性测试（P15/P16/P17）
    - **产出（新增）**: `apps/agent-console/src/features/agents/__tests__/conversationHistory.property.test.ts`
    - P15 (sort stability)、P17 (legacyMigration)；P16 通过 store action 直接测试（额外 it），或对纯的 `setCurrentConversationReducer` 纯函数做测试。
    - **Acceptance**: `cd apps/agent-console && npm run test -- --run`

  - [x]* 5.3 autogrow + autoscroll 属性测试（P18/P19）
    - **产出（新增）**:
      - `apps/agent-console/src/features/agents/__tests__/composerAutogrow.property.test.ts`
      - `apps/agent-console/src/features/agents/__tests__/autoScrollFollow.property.test.ts`
    - **Acceptance**: `cd apps/agent-console && npm run test -- --run`

- [x] 6. Wave 5 — Acceptance gate

  - [x] 6.1 Final checkpoint
    - **产出**: 无新增/修改代码
    - **Acceptance**:
      - `cd apps/agent-console && npm run lint`
      - `cd apps/agent-console && npm run build`
      - `cd apps/agent-console && npm run test -- --run`
      - 上述 3 条退出码均为 0，v1 / v2 的 29 个测试 + v3 新增属性测试全部通过。

## Property-to-Task Map

| Property | Invariant | Primary impl | PBT |
| -------- | --------- | ------------ | --- |
| P12 | parseSlashCommand TOTAL | 1.1 | 5.1 |
| P13 | parseSlashCommand idempotent | 1.1 | 5.1 |
| P14 | confirmed restDraft drops /cmd | 1.1 | 5.1 |
| P15 | sortConversationsByUpdatedAt stable desc | 1.2 | 5.2 |
| P16 | switch A→B→A preserves snapshot | 2.1 | 5.2 |
| P17 | legacyMigration deterministic | 1.2 | 5.2 |
| P18 | clampAutogrowHeight ∈ [40,200] | 1.3, 4.1 | 5.3 |
| P19 | computeFollowDecision semantics | 1.3, 4.2 | 5.3 |
