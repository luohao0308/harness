# Team UI Apple/Codex 风格审计与优化方案

## 结论

当前桌面 Team 页面功能结构完整，截图中没有发现明显遮挡、不可读或阻断操作的问题；主要问题是信息层级竞争和视觉密度分配，而不是能力缺失。建议保留现有 Team 数据、消息路由、三视图和响应式契约，只把首屏收敛成“团队身份 → 当前会话 → 一个按需辅助面板 → 输入”四层。

本次方案已连续执行 P0/P1/P2。Team 业务语义、API、SSE、mailbox、任务和目标状态保持不变，仅调整信息编排、展示样式、响应式断点和测试契约。

## 证据范围

- 用户截图：`/var/folders/j3/1pxq4hf53bn1df3r6mvmw3zw0000gp/T/codex-clipboard-701527fd-8d62-43b5-897c-cd4826f5fd4c.png`
- `apps/agent-console/src/app/ConsoleShell.tsx:343-369` — Electron Team 路由使用窄操作轨道，不渲染普通网页 ConsoleShell。
- `apps/agent-console/src/features/teams/pages/TeamPage/index.tsx:714-821` — Team 页面组合 Team rail、Team header、Agent tabs 和 workspace surface。
- `apps/agent-console/src/features/teams/components/TeamRail.tsx:24-88` — 团队列表 rail 固定约 `144px/152px`，列表项和创建按钮各自有边框/背景。
- `apps/agent-console/src/features/teams/pages/TeamPage/TeamHeader.tsx:76-198` — 顶部同时呈现团队身份、视图切换、目标摘要、工具、添加成员和任务板。
- `apps/agent-console/src/features/teams/pages/TeamPage/TeamWorkspaceSurface.tsx:47-81` — 协作视图默认 `80/20`，任务图默认 `56/44`，辅助面板通过分隔线和圆形折叠按钮出现。
- `apps/agent-console/src/features/teams/pages/TeamPage/DesktopTeamMemberRoster.tsx:32-127` — 会话底部再次展示完整成员列表、进度条、状态和任务信息。
- `apps/agent-console/src/features/teams/pages/TeamPage/DesktopTeamInspector.tsx:105-263` — 右侧检查器再展示成员选择、动态/任务 tabs 及连续活动卡片。
- `apps/agent-console/src/features/teams/pages/TeamPage/TeamAgentTabs.tsx:57-172` — Agent tabs 仍作为完整成员切换器，包含状态、任务数、未读数和编辑/拖拽 affordance。
- `apps/agent-console/src/features/teams/pages/TeamPage/AgentColumn.tsx:394-481` — 会话列有独立列边框、标题栏、头像、角色/状态徽标和模型元数据。
- `docs/design/desktop/team-mode-workspace.md:35-118` — 既有产品合同已明确聊天优先、协作 `80/20`、任务图 `56/44`、roster 属于会话补充、网页多列不变。
- `.omx/artifacts/visual-ralph/desktop-team-mode/desktop-collaboration.png` — 现有实现的方向性视觉基线。

## 观察与推断

### 观察（截图直接可见）

1. 左侧同时出现全局操作轨道和团队列表，顶部又重复团队身份；右侧再出现团队动态，主会话边界不够突出。
2. 中央消息区上下留白较大，但顶部操作和右侧活动卡片较密，纵向节奏不一致。
3. rail、header、Agent tabs、消息气泡、成员项、inspector 活动项和 composer 都有独立描边或容器感，连续平面被切碎。
4. 时间、输入/输出统计、模型元数据、占位文字等使用较浅灰色与小字号，重要辅助信息的可读性偏弱。
5. 折叠分栏、全屏、底部设置等动作主要依赖图标；团队名在窄 rail 中截断为省略号。
6. 蓝色同时表达选中、运行、信息、边框和 tab 下划线；语义层次略混。

### 推断（由代码与截图共同支持）

1. 视觉拥挤的主要来源是“同一成员信息被三处并列呈现”：Agent tabs、会话 roster、右侧 inspector 成员选择。它们都有状态/任务信息，导致首屏扫描路径重复。
2. 顶部 `TeamHeader` 将目标 drift/fix/budget、工具数量、添加成员、任务板和视图切换放在同一行，窗口变窄时会发生 `flex-wrap`，主标题与动作权重进一步竞争。
3. 右侧 inspector 以最多 12 条活动生成连续卡片；这更像事件流而不是按需上下文，容易把“当前对话”降为背景。
4. 现有合同已经禁止 Dashboard-first 和卡片堆叠，因此优先级应是信息编排/收敛，而不是新增视觉层或新依赖。

## 优先级方案

### P0：先让首屏只服务当前会话

- `TeamHeader` 收敛为：返回、团队名/在线状态、`协作 / 任务图 / 多列`、一个更多菜单。目标只保留状态和 `完成/总数`；`drift / fix / budget` 移入目标详情。
- 保留 `TeamAgentTabs` 作为唯一的成员切换入口。协作视图的 roster 改成轻量摘要，默认只列姓名、状态、当前任务和短进度，不再重复完整任务计数、状态徽标和第二套成员选择。
- inspector 默认收起或只显示“最近一条活动 + 当前成员任务”；完整活动流通过“查看全部”进入抽屉/面板。任务图继续是独立视图，不与活动流同时出现。
- 保持 composer 常驻，消息与 composer 使用同一稳定阅读列；不要通过增加 panel/card 让空白区变成 dashboard。

### P1：建立 Codex 式连续平面

- 大区块统一白底/相邻中性色，保留 `1px` 分隔线；去掉 Team rail、roster、inspector 活动项和消息气泡的多重阴影/高对比描边。
- 选中态只使用淡蓝底 + 单一焦点环；运行/成功/等待/失败保留文字徽标，颜色只作辅助，不让蓝色承担所有语义。
- 消息采用 `max-width: 760px` 阅读列和 8/16/24px 节奏；空状态使用短提示，不留整屏无意义垂直空白。
- 正文和关键状态最低使用 `slate-700` 级别对比度；`slate-500` 以下仅用于时间、次要统计和禁用态。
- 图标按钮补齐 `aria-label`/tooltip；折叠按钮在首次展示时提供“收起团队检查器”等可见文字提示或状态说明。

### P2：统一语言与响应式细节

- 面向用户的 `Leader`、`default`、英文状态和命令摘要统一中文优先；保留模型/工具原始 ID 时降到辅助元数据层。
- `1024-1199px` 保留会话和 composer 的可用最小宽度，隐藏 rail 非必要标题文字；团队名使用完整 tooltip，避免只能看到省略号。
- 取消持续 `animate-pulse` 作为成员运行常态，改为静态“执行中”文本/图标，动画只用于短暂切换。
- 移动端沿用现有单列行为；只验证 Team route 不产生文档级水平溢出，任务图在窄屏作为临时全幅面板。

## 目标布局

```text
窄操作轨道  |  团队 rail（可收窄） |  团队名 · 状态 · 视图切换 · 更多
                                      ├─ 唯一 Agent tabs
                                      ├─ 中央会话阅读列
                                      │    └─ 轻量成员摘要（可折叠）
                                      └─ composer（与阅读列同宽）
                                      ↘ 按需 inspector / 任务图
```

建议 token：页面 `#ffffff`，辅助面 `#f7f8fa`，分隔 `slate-200`，正文 `slate-700`，标题 `slate-950`，选中 `blue-50`，焦点环 `blue-500`；圆角最多 `8px`，大区块不使用阴影，默认会话阅读列上限 `760px`。

## 实施顺序与验收

1. 先做 `TeamHeader` 信息收敛和 `TeamAgentTabs`/roster 职责拆分，不改 API、SSE、任务或 mailbox 语义。
2. 再做 `AgentColumn`、roster、inspector 的边框/间距/对比度收敛，补图标 tooltip 与完整团队名提示。
3. 最后做中文术语和窄屏断点微调。

每一步都应运行：

```bash
cd apps/agent-console
npx vitest run src/features/teams/__tests__/TeamPages.test.tsx
npm run lint -- --pretty false
npm run build
```

视觉验收：`1440x900` 协作/任务图/多列、`390x844` 浏览器单列；无文档级水平溢出，消息阅读列稳定，composer 可用，协作/任务图方向性视觉评分保持 `>=90`。本方案不要求复制参考图品牌、头像或窗口 chrome。

## 实施证据（2026-08-13）

- P0 已完成：顶部成员新增、目标控制收进“更多团队操作”；目标详情保留偏差/纠偏/预算；Agent tabs 统一为成员切换入口；协作 roster 改为非交互轻量摘要；检查器移除重复成员选择器并改为连续活动列表。
- P1 已完成：Team 消息与 composer 使用稳定 `760px` 阅读列；Team 消息启用无阴影、轻边框的 quiet 变体；步骤、运行链接、空状态和辅助面板改为连续中性色平面；分栏折叠按钮改为低对比矩形控件并保留 tooltip。
- P2 已完成：`Leader`、`default`、workspace mode 和状态文案中文优先；成员 tabs 移除持续 `animate-pulse` 并增加窄屏横向滚动渐隐提示；`1024-1199px` Team rail 收窄为图标态、保留完整 `title`；390px Web Team 隐藏强制收起的全局控制台栏，释放会话宽度；时间、统计和模型辅助文字提高到 `slate-500` 级别。
- 视觉证据目录：`.omx/artifacts/visual-ralph/desktop-team-mode-updated/`，包含 `desktop-collaboration.png`、`desktop-task-graph.png`、`desktop-columns.png`、`web-columns.png`、`web-mobile.png`。
- Visual Ralph 复核结果：最终方向性评分 `91/100`（PASS）；桌面信息层级 `93`、桌面一致性 `94`、溢出/遮挡 `96`、移动可用性 `84`。剩余差异集中在窄屏空间和辅助文字层级，已在最终迭代中处理。
- 回归证据：Team Vitest `27/27`、Team Playwright smoke `3/3`、Agent Console lint/typecheck 通过、Agent Console production build 通过、`python3 scripts/validate-docs.py`、`python3 scripts/check-markdown-links.py` 和 `git diff --check` 通过。

## 未决项

- 是否把团队 rail 在 Electron 中默认收窄到图标态；影响团队切换的可发现性。
- 目标摘要是否只显示“状态 + 完成/总数”；本方案建议将 drift/fix/budget 放入详情。
- roster 是否默认展开；本方案建议保留展开但仅显示轻量摘要。
