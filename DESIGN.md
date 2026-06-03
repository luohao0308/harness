# Design

## Source of truth
- Status: Active
- Last refreshed: 2026-06-02
- Primary product surfaces:
  - `hao` 本地 Agent CLI / TUI 的单输入、slash command、工具输出和权限提示
  - 全局 Console Shell 侧边栏与页面标题中文术语
  - `/tools` MCP / Skill 商店与能力安装流程
  - `/agents` Agent Studio 内的知识管理与能力配置弹窗
  - `/agents/:agentId/workspace` 会话级确认操作
  - `/teams/:teamId` 团队成员移除确认操作
  - `/runs/:runId` 运行详情中的依据审计、上下文组装与标记节省说明
  - `/observability` 依据质量与标记节省指标总览
  - `/token-savings` 标记节省总览与近期运行节省证据
  - `/settings/models` 模型网关、内置成本来源、模型切换与自定义供应商配置
- Evidence reviewed:
  - `README.md`
  - `docs/ai/agent-startup-context.md`
  - `omx_wiki/session-2026-05-17-agent-knowledge-p5-capability-registry.md`
  - `apps/agent-console/src/app/ConsoleShell.tsx`
  - `apps/agent-console/src/styles.css`
  - `apps/agent-console/src/components/ui/button.tsx`
  - `apps/agent-console/src/components/ui/QuickActionFAB.tsx`
  - `apps/agent-console/src/components/ui/config-dialog.tsx`
  - `apps/agent-console/src/features/tools/pages/ToolRegistryPage.tsx`
  - `apps/agent-console/src/features/agents/components/KnowledgeManagementPanel.tsx`
  - `apps/agent-console/src/features/agents/components/ChatSurface.tsx`
  - `apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx`
  - `apps/agent-console/src/features/teams/pages/TeamPage.tsx`
  - `apps/agent-console/src/features/runs/pages/RunDetailPage.tsx`
  - `apps/agent-console/src/features/runs/pages/RunHistoryPage.tsx`
  - `apps/agent-console/src/features/observability/pages/ObservabilityPage.tsx`
  - `apps/agent-console/src/features/observability/pages/TokenSavingsPage.tsx`
  - `apps/agent-console/src/features/settings/pages/ModelSettingsPage.tsx`
  - `apps/agent-console/src/features/settings/pages/__tests__/ModelSettingsPage.test.tsx`
  - `docs/cli/hao.md`
  - `services/api-server/app/cli/hao/tui.py`
  - `services/api-server/tests/test_hao_cli_v2.py`

## Brand
- Personality:
  - 专业、克制、可信，优先展示运行状态和下一步动作。
- Trust signals:
  - 中文优先术语
  - 明确的安装状态、审批阶段和测试结果
  - 不依赖浏览器原生弹窗
  - 所有状态来自后端或明确的本地交互结果
- Avoid:
  - 中英混排的按钮与状态
  - “点了没反应”的静默操作
  - 新手需要自行推断安装顺序
  - 浏览器 `alert/confirm/prompt`

## Product goals
- Goals:
  - 让新手能在 `/tools` 完成 MCP / Skill 的发现、安装、审批、挂载和验证。
  - 将所有关键交互改成中文、可解释、可回溯的反馈。
  - 统一确认弹窗与操作成功/失败提示，降低误操作焦虑。
- Non-goals:
  - 不重做整套视觉系统。
  - 不把现有页面改成营销型设计。
  - 不在前端伪造后端尚未提供的安装事实。
- Success signals:
  - 用户能看懂“当前在哪一步、下一步做什么、是否成功”。
  - 安装成功、失败、待审批、待安装、已安装一眼可辨。
  - 所有 destructive / branching 操作都通过自定义弹窗确认。
  - 模型页能先判断当前默认模型、健康状态和成本来源可用性，再执行切换或自定义配置。
  - 未配置真实 API Key 的模型不能直接切换，必须先进入配置弹窗。

## Personas and jobs
- Primary personas:
  - 新手运维或内部测试人员
  - 负责接入 MCP / Skill 的 Agent 管理员
  - 需要验证安装链路是否可用的产品/研发同学
- User jobs:
  - 找到合适的能力并安装到指定 Agent
  - 判断能力是否已安装、是否还要审批
  - 用具体案例快速验证 MCP 或 Skill 已生效
  - 在知识库、会话、团队页执行风险操作时获得清晰确认
- Key contexts of use:
  - 本地开发环境
  - 演示环境
  - 私有部署后的内部验证环境

## Information architecture
- Primary navigation:
  - 左侧导航保持控制台结构稳定，核心操作在页面主区完成。
- Core routes/screens:
  - `/tools`: 商店发现 + 安装工作台 + 高级生命周期
  - `/agents`: Agent Studio 中的知识和能力配置
  - `/agents/:agentId/workspace`: 会话与执行入口
  - `/teams/:teamId`: 团队编排与成员管理
  - `/runs`: 运行列表与入口摘要
  - `/token-savings`: 标记节省总览与近期运行证据
  - `/settings/models`: 当前默认模型摘要、内置成本来源、模型切换、自定义供应商弹窗、Fallback 和供应商观测
- Content hierarchy:
  - 先显示状态与结果，再显示配置输入
  - 先给“下一步”，再给底层包信息
  - 先给推荐测试案例，再给原始 JSON / ID
  - 模型页先显示当前默认和运行状态，再展示成本来源和配置操作；自定义模型配置只在弹窗出现，不常驻占用页面；价格源不可用时降级为中文告警而不是阻塞配置。

## Design principles
- Principle 1:
  - 中文优先，术语固定，减少双语噪音。
- Principle 2:
  - 每个高风险动作都要先确认，每个关键动作都要有结果反馈。
- Principle 3:
  - 新手路径优先于专家路径，专家能力保留在“高级生命周期”。
- Tradeoffs:
  - 保留 MCP 等必要缩写，但配合中文说明。
  - 原始 ID 和包元数据仍然展示，但降到结果卡片与摘要层。

## Visual language
- Color:
  - 继续沿用现有白底、石板灰、青蓝信息态、绿色成功态、琥珀警示态、红色风险态。
- Typography:
  - 维持控制台现有无衬线字体与等宽 ID 展示；中文按钮和状态优先短语化。
- Spacing/layout rhythm:
  - 以 8px 节奏为主，商店页强调卡片分区和步骤流。
  - `hao` TUI 采用 Claude Code 风格的 inline 终端节奏：不切换全屏 alternate screen，不呈现编辑器式大画布；欢迎卡、主会话、底部 `›` 输入行和轻量状态留在当前 shell 输出流里。底部状态必须包含当前模型、模型强度、compact 圆环、输出风格、审批数和命令数。工具工作台只按需作为底部 drawer 出现，不默认右侧分屏。
- Shape/radius/elevation:
  - 使用现有圆角卡片与轻阴影，不引入新材质语言。
- Motion:
  - 点击与加载反馈以轻量状态切换、toast、按钮忙碌文案为主。
- Imagery/iconography:
  - 继续使用 Lucide 图标，图标服务于状态理解，不单独承担含义。

## Components
- Existing components to reuse:
  - `hao` TUI 的 `SLASH_COMMANDS` 命令 catalog
  - `Button`
  - `Badge`
  - `Card`
  - `ConfigDialog`
  - `Input`
  - `MenuSelect`
  - `Table`
  - `Textarea`
- New/changed components:
  - `hao` Claude Code 风格 inline TUI：左右两栏 `hao Code` 欢迎卡、真实可用的 `/init` 和 `/release-notes` 启动页命令、底部 `›` composer、模型强度状态、compact 圆环、隐藏式工作台 drawer、主会话内工具/审批单行状态。
  - 统一确认弹窗
  - 全局操作反馈 toast/状态提示
  - 商店安装状态徽标与步骤提示
  - 模型设置摘要区、内置成本来源错误态与响应式宽表容器
  - 模型配置弹窗和模型页右下角快捷添加入口
- Variants and states:
  - 按钮必须体现默认、悬停、按下、忙碌、成功后反馈
  - 弹窗必须体现说明、确认、取消、关闭
  - 安装状态至少区分“未安装 / 待审批 / 待安装 / 已安装”
- Token/component ownership:
  - 继续复用 `Button`/`Badge`/`ConfigDialog` 体系，不新增第二套弹窗体系。

## Accessibility
- Target standard:
  - 保持当前控制台的键盘可达与语义弹窗基线。
- Keyboard/focus behavior:
  - 自定义弹窗支持 Esc 关闭、可见关闭按钮、明确焦点边界。
- Contrast/readability:
  - 维持当前高对比文本与状态底色。
- Screen-reader semantics:
  - 弹窗提供 `role="dialog"`、`aria-modal`、标题与说明关联。
- Reduced motion and sensory considerations:
  - 避免强动画，反馈以文字与颜色为主。

## Responsive behavior
- Supported breakpoints/devices:
  - 桌面优先，同时保证移动宽度下弹窗、商店列表与安装工作台可滚动使用。
- Layout adaptations:
  - 宽屏采用商店列表 + 安装工作台双栏；窄屏允许堆叠。
- Touch/hover differences:
  - 不能依赖 hover 才能理解状态，点击后必须有显式反馈。

## Interaction states
- Loading:
  - 使用“同步中 / 安装中 / 审批中 / 测试中”等中文忙碌文案。
- Empty:
  - 明确说明“暂无匹配项 / 暂无可选文档 / 暂无能力包”。
- Error:
  - 错误信息直接显示并进入统一反馈层。
  - 模型成本来源 404 / 未启用时显示“成本来源暂不可用”和中文原因，避免裸露 `404: Not Found`。
- Success:
  - 成功提示要告诉用户“做成了什么”和“接下来还能做什么”。
- Disabled:
  - 禁用按钮应保留原因提示或上下文说明。
  - 未配置密钥的模型切换按钮不执行直接切换，使用“配置并启用”进入弹窗。
- Offline/slow network, if applicable:
  - 网络或源降级时保留本地推荐，并明确说明部分源不可用。

## Content voice
- Tone:
  - 直接、稳定、说明式，不喊口号。
- Terminology:
  - 固定使用“运行平台、标记节省、商店、安装、审批、挂载、测试、确认、知识源、团队成员”等中文。
- Microcopy rules:
  - 优先告诉用户结果和下一步。
  - 避免“Install / Approve / Enable / verified”裸英文。
  - 缩写首次出现时补中文解释，后续可直接使用。

## Implementation constraints
- Framework/styling system:
  - React 18 + TypeScript + Tailwind CSS
  - `hao` CLI 默认使用 Rich terminal loop 保持在当前 shell 输出流；Textual 组件只作为内部/后备实现面，不应作为默认全屏编辑器式界面。
  - `hao` CLI 的 `/compact` 与 `/compress` 是同一压缩入口；状态区用 `○/◔/◑/◕/◉/●` 表示本地 active-path compact 比例，不伪造真实 token 成本。
  - `hao` CLI 的真实终端输入依赖终端 echo，不额外重复打印用户消息；UTF-8 输入按字节安全解码，stream 401/403 失败显示 hao 自己的认证/权限提示。
  - `hao` 本地 API client 应忽略环境代理配置，保证 localhost Harness API 不被全局 SOCKS/HTTP 代理污染。
- Design-token constraints:
  - 继续沿用现有 `slate / emerald / amber / cyan / red` 语义色。
- Performance constraints:
  - 反馈组件保持轻量，不引入新依赖。
- Compatibility constraints:
  - 后端仍可能返回英文状态值，前端需做中文映射而不是改协议。
- Test/screenshot expectations:
  - 至少覆盖商店安装链路、确认弹窗链路、MCP 快速测试链路和核心中文文案。
  - 模型页布局调整需覆盖成功成本来源、价格源 404 降级、桌面和窄屏截图、无文档级水平溢出。

## Open questions
- [ ] 是否要把整个控制台从“中文优先”升级为“纯中文唯一文案”规范；当前先落在 MCP / Skill 商店和本次修改触达页面。
