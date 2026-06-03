# Design Document: agent-workspace-chat-v3-slash-history

## Overview

v3 在 v2 的全宽 聊天式 工作台基础上，解决「输入框过大、不自动跟滚、metadata 太抢焦点、没有历史对话、没有 slash 命令」这 6 条反馈。所有改动严格遵循既有约束：**不新增 runtime 依赖 / 不改 SSE 契约 / `useWorkspaceStore` 仅 additive 扩展 / TS 严格模式 / 保持 v1 + v2 的 15+1 property-based tests 全绿**。

核心思路：

- **Composer autogrow**：textarea ref + `scrollHeight` 写回 `style.height`，clamp 到 [40, 200]。
- **自动跟随滚动**：`useLayoutEffect` 同步贴底 + `IntersectionObserver` 监测底部 sentinel 决定 `autoFollow` 状态；`autoFollow === false` 时显示 `Jump_To_Latest_Button`。
- **Metadata 位置迁移**：`TopMetaBar` 删掉 `<MetadataStrip>`；`ChatSurface` 在 `ComposerToolbar` 上方渲染 `<MetadataStrip>` 作为次要行。
- **历史对话**：store additive 扩展 `conversations: ConversationSummary[]` + `currentConversationId: string`；新 persistence key `harness.workspace.v3.<agentId>.conversations`；左侧 `ConversationHistoryPanel` 渲染列表 + 新建 / 切换 / 删除。
- **Slash 命令**：新 pure lib `slashCommands.ts`（命令清单 + `parseSlashCommand` 解析器）+ 新组件 `SlashCommandMenu.tsx` 悬浮在 Composer 上方；Composer 的 `onKeyDown` 在 slash-open 状态下拦截方向键 / Enter / Esc / Tab 并派发回调。

## Architecture

### High-level component tree (v3)

```
<ConsoleShell>
  <div flex h-[calc(100vh-3.5rem)]>
    {/* LEFT: History panel (v3 新增，可折叠) */}
    <ConversationHistoryPanel
      collapsed={...}
      conversations={...}
      currentConversationId={...}
      onNewConversation={...}
      onSelectConversation={...}
      onDeleteConversation={...}
      onToggleCollapsed={...}
    />

    {/* MAIN: ChatSurface (v2 布局瘦身) */}
    <ChatSurface>
      <TopMetaBar>           {/* 单行紧凑：agent + model + mode + streaming + Stop + Inspector下拉 + Run Detail */}
      <ChatMessageList>      {/* useLayoutEffect 贴底 + IntersectionObserver sentinel + Jump 按钮 */}
      <footer sticky>
        {planGate.visible && <PlanApprovalPanel />}
        {/* v3: 不再渲染 ChatModeBanner */}
        <MetadataStrip />    {/* v3 位置：次要行、紧贴 Toolbar */}
        <ComposerToolbar />  {/* v3: 无 mode radio 区，其余控件保留 */}
        <ChatComposer>
          <SlashCommandMenu /* 悬浮在 textarea 上方，开合由 parseSlashCommand 控制 */ />
          <textarea /* autogrow 40–200px，Slash-open 时 Enter / ArrowDown 等被拦截 */ />
        </ChatComposer>
      </footer>
    </ChatSurface>

    {/* Inspector drawer unchanged */}
    <InspectorDrawer />
  </div>
  <SearchOverlay /> <ShortcutOverlay />
</ConsoleShell>
```

### Auto-scroll architecture (Req 2)

关键决策：**先贴底（useLayoutEffect）再监测（IntersectionObserver）**。

```
ChatMessageList:
  refs:
    scrollContainerRef: HTMLDivElement
    sentinelRef: HTMLDivElement (零高度、列表末尾)

  state:
    autoFollow: boolean = true
    sentinelVisible: boolean = true
    distanceToBottom: number = 0

  useEffect(mount):
    new IntersectionObserver((entries) => {
      for each: sentinelVisible = entry.isIntersecting
                 distanceToBottom = scrollHeight - scrollTop - clientHeight
                 autoFollow = sentinelVisible (即贴底 / 非贴底)
    }, { root: scrollContainerRef.current, threshold: 0, rootMargin: "0px" }).observe(sentinel)

  useLayoutEffect([contentSum]):
    if autoFollow && container:
      container.scrollTop = container.scrollHeight - container.clientHeight

  render:
    scroll container
      ...messages
      <div ref={sentinelRef} style={{height: 1}} />
    {(!autoFollow && distanceToBottom >= 200) && <JumpToLatestButton onClick={...} />}
```

- `contentSum` 定义为 `activePath.reduce((acc, n) => acc + n.content.length, 0)` — 比 v2 的 `pathLength + lastContentLength` 更敏感，任何节点内容变更都触发 layout effect。
- `autoFollow` 从 IntersectionObserver 直接读取，避免 v2 `shouldAutoScroll` 在 rAF 与 scrollHeight 更新之间的时序漂移。
- 用户主动向上滚动使 sentinel 离开视口 → `autoFollow = false`，后续 content 增长不再强行拉回底。
- 滚到底 sentinel 重现 → `autoFollow = true`，自动跟随恢复。
- `scrollToBottom()`（由 JumpToLatestButton 调用）使用 `behavior: "smooth"` + 直接把 `autoFollow` 置回 `true`。

### Composer autogrow architecture (Req 1)

```
ChatComposer:
  forwardedRef: HTMLTextAreaElement (external)
  internal textareaRef merged with forwarded

  const MIN_HEIGHT = 40
  const MAX_HEIGHT = 200

  autogrow(el):
    el.style.height = 'auto'                       // 先重置让 scrollHeight 正确
    const next = Math.min(Math.max(el.scrollHeight, MIN_HEIGHT), MAX_HEIGHT)
    el.style.height = `${next}px`
    el.style.overflowY = el.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden'

  useLayoutEffect([draft]):
    if textareaRef.current: autogrow(textareaRef.current)

  onChange(e):
    onDraftChange(e.target.value)
    // layout effect 会紧接着跑，不在 onChange 内重复触发
```

- 用 `useLayoutEffect([draft])` 而不是在 `onChange` 里同步做，原因：外部动作（Plan 修改、Slash `/tool` 插入、历史对话切换）也会改 draft，用 layout effect 能统一覆盖。
- `style.height = 'auto'` 的重置是经典套路，避免粘贴一大段后再删剩几字时 height 不收缩。

### Slash command architecture (Req 5)

**新模块 `lib/slashCommands.ts`**（pure）：

```typescript
export type SlashCommandName =
  | "plan" | "plan-md" | "chat" | "pin" | "clear"
  | "model" | "tool" | "search" | "help";

export type SlashCommand = {
  name: SlashCommandName;
  aliases: string[];          // e.g. plan: ["plan-md"]
  needsArgs: boolean;         // only tool = true
  zh: string;                 // description
  en: string;
  trigger: string;            // e.g. "/plan" (primary literal)
};

export const SLASH_COMMANDS: SlashCommand[] = [...];

export type SlashParseResult =
  | { kind: "none" }
  | {
      kind: "matching";
      prefix: string;        // e.g. "pl"
      candidates: SlashCommand[];
    }
  | {
      kind: "confirmed";
      command: SlashCommand;
      args: string;          // trimmed args text; "" when command has no args
      restDraft: string;     // draft with /command + space stripped
    };

export function parseSlashCommand(draft: string): SlashParseResult {
  // 1. draft 不以 '/' 起或包含换行 → { kind: "none" }
  // 2. 去掉首 '/'; 用第一个空格切成 head + args
  // 3. head 匹配不到任何 command.name 或 alias → { kind: "matching", candidates: prefix match }
  //    - candidates 过滤规则：每个 command 的 name / alias 以 head 的前缀开头（case-insensitive）
  // 4. head 精确匹配到 cmd，且（无 args 模式 || (有 args 模式 && args 非空)）
  //    → { kind: "confirmed", command, args, restDraft: "" }
  // 5. head 精确匹配到 needsArgs 的 cmd 但 args 空 → { kind: "matching" } 继续编辑
}

export function filterCommandsByPrefix(prefix: string): SlashCommand[] {
  const p = prefix.toLowerCase();
  return SLASH_COMMANDS.filter(cmd =>
    cmd.name.startsWith(p) ||
    cmd.aliases.some(a => a.startsWith(p)),
  );
}

export function replaceSlashPrefix(draft: string, commandName: SlashCommandName): string {
  // 用 "/commandName " 替换 draft 首部的 "/<prefix>" 段（直到第一个空格或末尾）
}
```

**`SlashCommandMenu.tsx`**：

```
props: {
  open: boolean
  candidates: SlashCommand[]
  activeIndex: number
  onHover: (i: number) => void
  onSelect: (cmd: SlashCommand) => void
}

render: absolute bottom-full mb-2 w-[360px] rounded-2xl border bg-white shadow-xl p-1
  {candidates.length === 0 ? <EmptyState /> : candidates.map((cmd, i) =>
    <button
      role="option"
      aria-selected={i === activeIndex}
      className={i === activeIndex ? "bg-slate-100" : "hover:bg-slate-50"}
      onMouseEnter={() => onHover(i)}
      onClick={() => onSelect(cmd)}
    >
      <span className="font-mono text-slate-900">{cmd.trigger}</span>
      <span className="text-slate-500">{text(cmd.zh, cmd.en)}</span>
    </button>
  )}
```

**`ChatComposer` 拦截**：

```
const slashState = parseSlashCommand(draft);
const slashOpen = slashState.kind === "matching" ||
                  (slashState.kind === "confirmed" && !wasJustConfirmed);

// activeIndex 随 candidates 变化 clamp
const [slashIndex, setSlashIndex] = useState(0);
useEffect(() => { setSlashIndex(0); }, [slashState.kind, (slashState as any).prefix]);

onKeyDown:
  if (slashOpen) {
    switch (event.key) {
      case "ArrowDown": event.preventDefault(); setSlashIndex(i => (i + 1) % candidates.length); return;
      case "ArrowUp":   event.preventDefault(); setSlashIndex(i => (i - 1 + len) % len); return;
      case "Enter":     event.preventDefault(); dispatch(candidates[slashIndex]); return;
      case "Escape":    event.preventDefault(); onDraftChange(""); return;
      case "Tab":       event.preventDefault(); onDraftChange(replaceSlashPrefix(draft, chosen)); return;
    }
  }
  // 普通 composer 语义继续
```

**动作分派（由 ChatSurface 传入 callback）**：

```
onSlashDispatch(cmd: SlashCommand, args: string):
  switch cmd.name:
    case "plan":   onWorkspaceModeChange("plan");      onDraftChange("")
    case "plan-md":  onWorkspaceModeChange("markdown_plan");onDraftChange("")
    case "chat":   onWorkspaceModeChange("chat");      onDraftChange("")
    case "pin":    if tail: togglePinned(tail.id);     onDraftChange("")
    case "clear":  onClearConversation();              onDraftChange("")
    case "model":  onOpenModelPicker();                onDraftChange("")
    case "tool":   onInsertMention(args);              // args = tool name (may be fuzzy)
    case "search": onOpenSearch();                     onDraftChange("")
    case "help":   onOpenShortcut();                   onDraftChange("")
```

关键：**命令分派后 `draft` 被清空（或被 `@tool ` 替换）**；`stream.start()` 不会被 slash 命令触发（用户仍需手动 Enter 一次）。

### Conversation history architecture (Req 4)

**Store 扩展**（additive only，不删除 v2 字段）：

```typescript
type ConversationSummary = {
  id: string;                        // uuidv4
  title: string;                     // 默认 "New conversation" / "新对话"
  created_at: string;                // ISO
  updated_at: string;                // ISO; 首条消息/切换时更新
  nodesById: Record<string, ConversationNode>;
  rootNodeId: string;
  activeLeafId: string;
  pinnedNodeIds: string[];
  dismissedPlanNodeIds: string[];
  draft: string;
  contextWindowTurns: number;
};

// additive fields on WorkspaceState:
conversations: ConversationSummary[];      // 默认 [genesisConversation]
currentConversationId: string;             // 初始 = conversations[0].id
historyPanelCollapsed: boolean;            // 持久化单独的 key

// additive actions:
newConversation(): string (returns new id)
setCurrentConversation(id: string): void   // 把 nodesById 等换成目标 conversation 的快照
deleteConversation(id: string): void       // 删除 + 若删的是当前则切到最新的一条；空列表则自动建
renameConversation(id: string, title: string): void   // additive, 预留
setHistoryPanelCollapsed(v: boolean): void
```

**同步机制**（保证"切换—修改—切换回来—数据还在"）：

`setCurrentConversation(id)` 的**两步**：

```
currentSnapshot = {
  nodesById, rootNodeId, activeLeafId, pinnedNodeIds,
  dismissedPlanNodeIds, draft, contextWindowTurns,
  updated_at: now,
}
// 1. 写回当前 conversation
conversations = conversations.map(c =>
  c.id === currentConversationId ? { ...c, ...currentSnapshot } : c)
// 2. 从目标 conversation 加载
target = conversations.find(c => c.id === id) ?? conversations[0]
set {
  nodesById: target.nodesById, rootNodeId: target.rootNodeId,
  activeLeafId: target.activeLeafId, pinnedNodeIds: target.pinnedNodeIds,
  dismissedPlanNodeIds: target.dismissedPlanNodeIds, draft: target.draft,
  contextWindowTurns: target.contextWindowTurns,
  currentConversationId: id,
}
```

**持久化**（300ms debounce subscribe，沿用 v2 写回机制但改目标 key）：

```
useWorkspaceStore.subscribe(state => {
  if (state._agentScope === null) return;
  debounce 300ms → {
    // 把 current conversation 的运行时状态合并写回 conversations
    const merged = state.conversations.map(c =>
      c.id === state.currentConversationId
        ? { ...c,
            nodesById: state.nodesById, rootNodeId: state.rootNodeId,
            activeLeafId: state.activeLeafId, pinnedNodeIds: state.pinnedNodeIds,
            dismissedPlanNodeIds: state.dismissedPlanNodeIds, draft: state.draft,
            contextWindowTurns: state.contextWindowTurns,
            updated_at: new Date().toISOString(),
            title: computeTitleFrom(state.nodesById, c.title),
          }
        : c
    )
    saveConversationsSnapshot(state._agentScope, {
      version: 2,
      conversations: merged,
      currentConversationId: state.currentConversationId,
    })
  }
})
```

**Legacy migration**：

```
onAgentScopeLoad(agentId):
  v3 = readConversationsSnapshot(agentId)
  if v3: restore v3 (streaming → paused)
  else:
    v2 = loadSnapshot(agentId)  // existing localPersistence.ts
    if v2: conversations = [legacyMigration(v2, now())]
           saveConversationsSnapshot(...)
           clearSnapshot(agentId)  // remove v2 key
    else: conversations = [genesisConversation()]
```

`legacyMigration(v2Snapshot, now)` 纯函数：

```
title = pickTitleFrom(v2Snapshot.nodesById) ?? "Imported"
return {
  id: newUuid(),
  title,
  created_at: now,
  updated_at: now,
  nodesById: rewriteStreaming(v2Snapshot.nodesById),
  rootNodeId: v2Snapshot.rootNodeId,
  activeLeafId: v2Snapshot.activeLeafId,
  pinnedNodeIds: v2Snapshot.pinnedNodeIds,
  dismissedPlanNodeIds: v2Snapshot.dismissedPlanNodeIds,
  draft: v2Snapshot.draft,
  contextWindowTurns: v2Snapshot.contextWindowTurns,
}
```

### Metadata position migration (Req 3)

`TopMetaBar` 删掉 `<MetadataStrip>`。`ChatSurface` 在 footer 内部、`<PlanApprovalPanel>` 下方、`<ComposerToolbar>` 上方插入 `<MetadataStrip>`：

```tsx
<footer sticky>
  {planGate.visible && <PlanApprovalPanel />}
  <MetadataStrip tail={tail} activeRunId={activeRunId} onOpenRunDetail={...} />  {/* 新位置 */}
  <ComposerToolbar />
  <ChatComposer />
</footer>
```

`MetadataStrip` 本身**不改**；字段格式、P8 语义、双语文案全部保持。新增视觉微调：外层 className `text-[11px] text-slate-400`（v2 已经是 `text-xs text-slate-500`，v3 再降一档），但组件内部不硬编码色号，由父 wrapper 包一层 `<div className="text-[11px] text-slate-400">` 即可。

### Inspector menu merge (Req 6.2)

原三按钮合并为一个下拉：

```tsx
<InspectorMenuButton onOpenInspector={onOpenInspector} />

// 组件内部：
const [open, setOpen] = useState(false);
useOutsideClick(ref, () => setOpen(false), open);
<button onClick={() => setOpen(o => !o)} aria-haspopup="menu" aria-expanded={open}>
  <PanelRight /> {text("Inspector", "Inspector")} <ChevronDown />
</button>
{open && <div role="menu" absolute>
  <button onClick={() => { onOpenInspector("metadata"); setOpen(false); }}>Metadata</button>
  <button onClick={() => { onOpenInspector("artifacts"); setOpen(false); }}>Artifacts</button>
  <button onClick={() => { onOpenInspector("runtime"); setOpen(false); }}>Runtime</button>
</div>}
```

### ChatModeBanner removal (Req 6.3)

`ChatSurface.tsx` 的 JSX 中移除 `{workspaceMode !== "chat" && <ChatModeBanner ... />}`；保留文件与 import 可选。改动侧链：v2 `ComposerToolbar` 右侧的 mode radiogroup 也移除（由 slash 命令代替）。

### ChatComposer mode radio removal (Req 6.7)

v2 `<ChatComposer>` 底部的 `<div role="radiogroup">` 含 chat/plan-md/plan 三个 chip。v3 移除这一块。保留 `mode` / `onChangeMode` props 以向后兼容（`ChatSurface` 不再传 `onChangeMode` 给渲染 UI，但 prop 仍在类型中，向后兼容）。

## Components

### New / modified files (summary)

| Path | Status | Purpose |
| ---- | ------ | ------- |
| `src/features/agents/lib/slashCommands.ts` | new | `SLASH_COMMANDS` 清单 + `parseSlashCommand` / `filterCommandsByPrefix` / `replaceSlashPrefix` 纯函数 |
| `src/features/agents/lib/conversationHistory.ts` | new | `ConversationSummary` 类型 + `sortConversationsByUpdatedAt` + `computeConversationTitle` + `legacyMigration` + `genesisConversation` + `saveConversationsSnapshot` / `readConversationsSnapshot` |
| `src/features/agents/components/SlashCommandMenu.tsx` | new | 悬浮候选列表 |
| `src/features/agents/components/ConversationHistoryPanel.tsx` | new | 左侧抽屉 |
| `src/features/agents/components/JumpToLatestButton.tsx` | new | 圆形 icon-only 悬浮按钮 |
| `src/features/agents/components/InspectorMenu.tsx` | new | Inspector 下拉（Metadata/Artifacts/Runtime 合并） |
| `src/stores/workspaceStore.ts` | modified (additive) | 新 `conversations`/`currentConversationId`/`historyPanelCollapsed` 字段 + 对应 actions + persistence subscribe 改写 |
| `src/features/agents/components/ChatComposer.tsx` | modified | autogrow + slash menu 拦截、移除 mode radio |
| `src/features/agents/components/ChatMessageList.tsx` | modified | useLayoutEffect 贴底 + IntersectionObserver sentinel + jump button |
| `src/features/agents/components/ChatSurface.tsx` | modified | metadata 位置迁移、删除 ChatModeBanner 渲染、Inspector 按钮合并、slash 命令回调、conversations 同步 |
| `src/features/agents/pages/AgentWorkspacePage.tsx` | modified | 渲染 `ConversationHistoryPanel`、切换 conversations、legacy 迁移、model picker open 状态、新 persistence 读写 |
| `src/features/agents/__tests__/slashCommands.property.test.ts` | new (PBT) | P12 / P13 / P14 属性测试 |
| `src/features/agents/__tests__/conversationHistory.property.test.ts` | new (PBT) | P15 / P16 / P17 属性测试 |
| `src/features/agents/__tests__/composerAutogrow.property.test.ts` | new (PBT) | P18 属性测试（对纯函数 `clampAutogrowHeight`） |
| `src/features/agents/__tests__/autoScrollFollow.property.test.ts` | new (PBT) | P19 属性测试（对纯函数 `computeFollowDecision`） |

### Component interface contracts

#### `SlashCommandMenu`

```typescript
type SlashCommandMenuProps = {
  open: boolean;
  candidates: SlashCommand[];
  activeIndex: number;
  onHover: (index: number) => void;
  onSelect: (cmd: SlashCommand) => void;
};
```

#### `ConversationHistoryPanel`

```typescript
type ConversationHistoryPanelProps = {
  collapsed: boolean;
  conversations: ConversationSummary[];
  currentConversationId: string;
  onNewConversation: () => void;
  onSelectConversation: (id: string) => void;
  onDeleteConversation: (id: string) => void;
  onToggleCollapsed: () => void;
};
```

布局：

```
<aside className={collapsed ? "w-0 overflow-hidden" : "w-[260px] shrink-0"}>
  <header: "历史对话 / History" + 新建按钮 + 折叠按钮>
  <ul>
    {sortConversationsByUpdatedAt(conversations).map(c =>
      <li className={c.id === currentConversationId ? "bg-slate-100 ring-1 ring-slate-300" : "hover:bg-slate-50"}>
        <button onClick={() => onSelectConversation(c.id)} className="flex-1 truncate">
          <span>{c.title}</span>
          <time>{formatRelativeTime(Date.parse(c.updated_at), Date.now(), locale)}</time>
        </button>
        <button onClick={() => onDeleteConversation(c.id)} aria-label="删除对话 / Delete">
          <Trash2 />
        </button>
      </li>
    )}
  </ul>
</aside>
```

#### `JumpToLatestButton`

```typescript
type JumpToLatestButtonProps = {
  onClick: () => void;
};
// 渲染：absolute right-6 bottom-28 rounded-full bg-slate-900 text-white p-2 shadow
```

#### `InspectorMenu`

```typescript
type InspectorMenuProps = {
  onOpenInspector: (section: InspectorSection) => void;
};
```

### Modified interfaces

#### `useWorkspaceStore` (additive)

```typescript
type WorkspaceState = {
  // ... v1 + v2 fields unchanged ...

  // v3 additive
  conversations: ConversationSummary[];
  currentConversationId: string;
  historyPanelCollapsed: boolean;

  // v3 additive actions
  newConversation: () => string;
  setCurrentConversation: (id: string) => void;
  deleteConversation: (id: string) => void;
  renameConversation: (id: string, title: string) => void;
  setHistoryPanelCollapsed: (collapsed: boolean) => void;
  hydrateFromConversations: (
    snapshot: { conversations: ConversationSummary[]; currentConversationId: string }
  ) => void;
};
```

`reset()` 清空当前对话但保留 conversations 列表结构；额外提供 `resetCurrentConversation()`：将 `currentConversationId` 指向的 `ConversationSummary` 重置为初始状态（但不删除它）。

#### `ChatComposer`

新 props（additive）：

```typescript
type ChatComposerProps = {
  // ... v2 props ...

  // v3 additive
  onSlashDispatch?: (cmd: SlashCommand, args: string) => void;
  onSlashStateChange?: (open: boolean) => void;  // optional，供外部控制 focus 等
};
```

`mode` / `onChangeMode` 保留但不渲染 UI。

#### `ChatMessageList`

无新 props（依赖现有 activePath content 变化触发 layout effect）。

## Data Models

### `ConversationSummary`

```typescript
export type ConversationSummary = {
  id: string;                                           // uuid or crypto.randomUUID fallback
  title: string;
  created_at: string;                                    // ISO
  updated_at: string;
  nodesById: Record<string, ConversationNode>;
  rootNodeId: string;
  activeLeafId: string;
  pinnedNodeIds: string[];
  dismissedPlanNodeIds: string[];
  draft: string;
  contextWindowTurns: number;
};
```

### `ConversationsSnapshot` (persisted)

```typescript
export type ConversationsSnapshot = {
  version: 2;
  conversations: ConversationSummary[];
  currentConversationId: string;
};
```

storage key: `harness.workspace.v3.<agentId>.conversations`

### `SlashCommand` / `SlashParseResult`

见上文 §Slash command architecture。

## Error Handling

| Scenario | Behaviour |
| -------- | --------- |
| `localStorage` 写失败（配额/禁用）| `saveConversationsSnapshot` 复用 v2 `saveSnapshot` 的模块级 `skipWrites` flag；失败时 console.warn 一次、返回 false；内存仍正常工作。 |
| 读 v3 key 解析失败 / version 不匹配 | `readConversationsSnapshot` 返回 null；上游回退到 v2 legacy migration 或 genesis。 |
| Legacy 迁移 v2 快照损坏 | `loadSnapshot` 已在 v2 层做防御；`legacyMigration` 再做 `isNodesRecord` 等浅校验，损坏时回退到 genesis。 |
| Slash 命令解析器对超长 / 非法 UTF-16 | `parseSlashCommand` 纯字符串操作，不抛异常；最坏返回 `{ kind: "matching", candidates: [] }`（空候选） |
| IntersectionObserver 在 JSDOM 中缺失 | `typeof IntersectionObserver === "undefined"` 时 fallback 为 `autoFollow = true` + 无观察；测试环境下不影响组件渲染。 |
| 自动增高的 `scrollHeight` 为 0 | `clampAutogrowHeight` 先 `Math.max(scrollHeight, MIN_HEIGHT)` 再 `Math.min(..., MAX_HEIGHT)`，NaN / 非数字 fallback 为 MIN_HEIGHT。 |
| 删除当前 conversation 后空列表 | `deleteConversation` 在空列表自动创建一条 genesis 并切换 |
| 并发切换（debounce 期间再切）| 写回总是基于 "当前快照 = 当前 store state"，debounce 在 300ms 合并，切换动作本身是同步的，不会产生数据竞态 |

## Testing Strategy

### Layer 1 — Pure function unit tests
- `parseSlashCommand`: edge cases (`""` / `"/"` / `"/plan"` / `"/plan extra"` / `"/pla"` / `"/plan-md"` / `"/plan-md"` / `"/tool"` / `"/tool curl"` / 换行 / emoji / 超长)
- `filterCommandsByPrefix`: 大小写、前缀、别名
- `replaceSlashPrefix`: 确保替换第一段不破坏后续 args
- `sortConversationsByUpdatedAt`: 稳定性 / 倒序
- `computeConversationTitle`: 首条 user message 前 40 字符 / fallback / 多字节
- `legacyMigration`: 输入 v2 snapshot → 输出单元素数组
- `clampAutogrowHeight`: [40, 200] 闭区间 clamp
- `computeFollowDecision`: 基于 sentinel 可见 / distanceToBottom 决策

### Layer 2 — Property-based tests (fast-check)

| Property | Invariant | File |
| -------- | --------- | ---- |
| P12 | `parseSlashCommand` TOTAL + 返回 kind 正确 | `slashCommands.property.test.ts` |
| P13 | `parseSlashCommand` idempotent | 同上 |
| P14 | Confirmed 的 `restDraft` 不含 `/command` 前缀 | 同上 |
| P15 | `sortConversationsByUpdatedAt` 稳定倒序 | `conversationHistory.property.test.ts` |
| P16 | 切换 A → B → A 后 A 数据深等价 | 同上（模拟两次 `setCurrentConversation`） |
| P17 | `legacyMigration` 对任意合法 v2 snapshot → 单元素数组，字段一致 | 同上 |
| P18 | `clampAutogrowHeight(any)` ∈ [40, 200] | `composerAutogrow.property.test.ts` |
| P19 | `computeFollowDecision` 对 `autoFollow === true` 返回 shouldScroll=true；false 时返回 false | `autoScrollFollow.property.test.ts` |

### Layer 3 — Regression
- v1 + v2 的 8 个现有测试文件（29 tests）继续通过。

### Layer 4 — Manual smoke
a. 打开 /agents/:id/workspace，左侧 History 面板可见，右侧可折叠
b. 新建对话按钮创建空对话并切换
c. 发送消息后 title 自动取首条 user 消息前 40 字符
d. 切换对话保留各自快照
e. 删除当前对话自动切到最新的另一条
f. 输入 `/` 弹 menu，`/plan` 切换到 Plan 模式且 draft 清空
g. `/tool curl` 插入 `@curl `
h. Composer 默认 1 行高，粘贴 20 行后内部滚动
i. 流式过程中页面保持贴底；向上滚后出现 Jump 按钮
j. Metadata 次要行在 Composer 上方显示

## Migration / Rollout

- localStorage v2 key → v3 key 的一次性迁移在 `AgentWorkspacePage` 挂载时完成（幂等：再次挂载不会重复迁移，因为 v2 key 已被删除）。
- 如需回滚 v3 → v2，只需重置 v3 key，前端会用空 genesis 启动；v2 key 仍保留在磁盘的用户会得到一条"Imported"对话。

## Non-Goals (reiterate)

- 不改后端 SSE 契约 / Nginx 配置 / Run Detail 页面
- 不引入新 runtime 依赖（uuid 用 `crypto.randomUUID()` 或 fallback；相对时间用 v2 已有 `relativeTime.ts`）
- 不做对话重命名 UI
- 不做跨 tab 实时同步
