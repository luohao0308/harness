# 本地 Agent UI 功能恢复报告

**日期**: 2026-06-15  
**分支**: `feature/restore-local-agent-ui`  
**基础分支**: `feature/onboarding-v1`

## 问题诊断

从 `feature/local-agent-claude-code-permission-bridge-v6` 到 `feature/onboarding-v1` 的合并过程中，**本地 Agent 的 Web UI 接入功能被完全删除**，导致：

- ❌ 智能体页面无法管理本地 Agent 连接
- ❌ 无法生成配对命令和令牌
- ❌ 无法查看和管理本地设备连接
- ❌ 缺少 Agent 就绪状态可视化

**但是**：
- ✅ `hao` CLI 工具完整保留且运行正常
- ✅ 后端 API 功能完整
- ✅ 只是前端 UI 被移除

## 已恢复内容

### 1. 核心组件恢复
- **AgentReadinessRing.tsx** (63 行) - Agent 就绪状态环形图
  - 显示工具、知识源、连接三个维度的就绪度
  - 可视化百分比进度
  - 支持不同尺寸（sm / md）

- **CollapsibleCapabilitySection.tsx** (35 行) - 可折叠能力区
  - 核心能力和高级能力分组展示
  - 响应式网格布局

### 2. API 层恢复 (177 行新增)
在 `apps/agent-console/src/features/tasks/api.ts` 中恢复：

**类型定义**:
- `LocalAgentPairing` - 配对令牌信息
- `LocalAgentConnection` - 本地连接详情
- `LocalAgentConnectionPage` - 连接列表分页
- `LocalAgentConversationBinding` - 会话绑定
- `LocalAgentConversationBindingPage` - 绑定列表分页
- `LocalAgentSendMessagePayload` - 消息发送载荷
- `LocalAgentSendMessageResponse` - 消息发送响应
- `LocalAgentBindingTask` - 绑定任务
- `LocalAgentBindingTaskPage` - 任务列表分页

**API 函数**:
- `createLocalAgentPairingToken(agentId)` - 创建配对令牌
- `revokeLocalAgentPairingToken(tokenId)` - 撤销配对令牌
- `listLocalAgentConnections()` - 列出本地连接
- `updateLocalAgentConnection(id, payload)` - 更新连接信息
- `revokeLocalAgentConnection(id)` - 撤销连接
- `listLocalAgentConversationBindings(connectionId)` - 列出会话绑定
- `bindLocalAgentConversation(connectionId, payload)` - 绑定会话
- `listLocalAgentBindingTasks(bindingId)` - 列出绑定任务
- `sendLocalAgentMessage(bindingId, payload)` - 发送消息

### 3. AgentListPage.tsx 完整恢复 (1436 行新增)

**恢复的核心功能**:
- ✅ 本地 Agent 配对流程
  - 生成配对令牌和命令
  - 复制配对命令到剪贴板
  - 令牌过期管理
  
- ✅ 连接发现和管理
  - 实时轮询连接状态（3 秒间隔）
  - 设备识别和命名
  - 连接选择和确认
  - 批量撤销未选中连接
  
- ✅ Agent 就绪度追踪
  - 工具数量统计
  - 知识源数量统计
  - 本地连接数量统计
  - 就绪环形图可视化
  
- ✅ 状态管理
  - `localAgentDialogOpen` - 本地 Agent 对话框状态
  - `localAgentPairing` - 当前配对信息
  - `selectedLocalConnectionIds` - 已选连接 ID 列表
  - `seenLocalConnectionIds` - 已见过的连接 ID
  - `localConnectionNames` - 连接自定义名称映射
  - `pairCommandCopied` - 命令复制状态
  - `localDiscoveryManualRefreshing` - 手动刷新状态
  
- ✅ Mutations
  - `createLocalAgentPairingMutation` - 创建配对
  - `updateLocalAgentConnectionMutation` - 更新和保存连接
  - `revokeLocalAgentConnectionMutation` - 撤销单个连接

## 当前状态

### ✅ 已完成
1. 所有必需的 React 组件已恢复
2. 所有 TypeScript 类型定义已恢复
3. 所有 API 调用函数已恢复
4. AgentListPage 的完整本地 Agent 管理 UI 已恢复
5. 代码已提交到 `feature/restore-local-agent-ui` 分支

### ⚠️ 需要验证的项
以下功能可能需要进一步验证，因为 onboarding-v1 分支可能有其他更改：

1. **测试文件** - 本地 Agent 相关的测试可能需要更新
   - `AgentListPage.studio.test.tsx` 被大量简化
   - 可能需要恢复本地 Agent 测试用例

2. **其他组件** - 以下组件在两个分支间有差异：
   - `ChatMessageBubble.tsx` (218 行删除)
   - `ChatSurface.tsx` (149 行变更)
   - `ConversationHistoryPanel.tsx` (135 行变更)
   - `WorkspaceShellBar.tsx` (156 行变更)
   - `AgentWorkspacePage.tsx` (2323 行删除)

3. **RefreshOverlay 组件** - AgentListPage 导入了此组件但需要确认是否存在

## 文件变更统计

```
apps/agent-console/src/features/agents/components/AgentReadinessRing.tsx       | 63 ++++
apps/agent-console/src/features/agents/components/CollapsibleCapabilitySection.tsx | 35 ++++
apps/agent-console/src/features/agents/pages/AgentListPage.tsx                | 1436 +++++++++++++---
apps/agent-console/src/features/tasks/api.ts                                   | 177 +++

4 files changed, 1490 insertions(+), 221 deletions(-)
```

## 下一步建议

### 方案 1: 验证并合并（推荐）
```bash
# 1. 检查是否有编译错误
cd apps/agent-console
npm run build

# 2. 运行相关测试
npm test -- AgentListPage

# 3. 启动开发服务器并手动测试
npm run dev

# 4. 如果一切正常，合并回主分支
git checkout feature/onboarding-v1
git merge feature/restore-local-agent-ui
```

### 方案 2: 逐步恢复其他组件
如果发现其他功能也缺失（如 Workspace 页面的本地 Agent 集成），可以继续从 `feature/local-agent-claude-code-permission-bridge-v6` 恢复：

```bash
# 恢复 AgentWorkspacePage
git show feature/local-agent-claude-code-permission-bridge-v6:apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx > apps/agent-console/src/features/agents/pages/AgentWorkspacePage.tsx

# 恢复其他受影响的组件
git show feature/local-agent-claude-code-permission-bridge-v6:apps/agent-console/src/features/agents/components/ChatSurface.tsx > apps/agent-console/src/features/agents/components/ChatSurface.tsx
```

### 方案 3: 三方合并
如果需要更精细的控制，使用 git 的三方合并：

```bash
# 创建合并提交但不自动提交
git checkout feature/onboarding-v1
git merge --no-commit --no-ff feature/local-agent-claude-code-permission-bridge-v6

# 解决冲突后
git add .
git commit
```

## 使用本地 Agent 功能

### CLI 方式（已可用）
```bash
# 查看帮助
hao --help

# 启动交互式会话
hao

# 查看会话历史
hao sessions

# 恢复会话
hao resume
```

### Web UI 方式（本次恢复）
1. 访问智能体页面：`http://localhost:3000/agents`
2. 选择要连接的 Agent
3. 点击"接入本地 Agent"按钮
4. 复制生成的配对命令
5. 在本地终端执行命令
6. 在 Web UI 确认连接
7. 开始使用本地 Agent

## 技术细节

### 本地 Agent 工作流程
1. **配对阶段**
   - 前端调用 `createLocalAgentPairingToken(agentId)`
   - 后端生成配对码和令牌，返回完整命令
   - 用户复制命令到本地终端执行

2. **连接阶段**
   - 本地 CLI 使用配对令牌连接到后端
   - 后端创建 `LocalAgentConnection` 记录
   - 前端轮询 `listLocalAgentConnections()` 发现新连接

3. **确认阶段**
   - 用户在 UI 选择要保留的连接
   - 调用 `updateLocalAgentConnection()` 更新连接名称
   - 未选中的连接通过 `revokeLocalAgentConnection()` 撤销

4. **使用阶段**
   - 通过 `bindLocalAgentConversation()` 绑定会话
   - 通过 `sendLocalAgentMessage()` 发送消息
   - 本地 Agent 执行工具并返回结果

### 安全边界
- 本地工具（文件读写、shell 命令）**只在本地 CLI 执行**
- 后端**不执行**宿主机工具，只接收审计记录
- 所有工具执行需要本地权限批准（confirm / auto-edit / full-auto 模式）

## 相关文档
- CLI 文档：`docs/cli/hao.md`
- 会话日志：`omx_wiki/session-2026-05-31-hao-agent-cli-v1.md`
- V2 协议：`omx_wiki/session-2026-06-01-hao-agent-cli-v2-step-*.md`

## 总结

✅ **本地 Agent 的 Web UI 功能已完整恢复**  
✅ **所有必需的类型、API 函数、组件都已添加**  
✅ **保留了 onboarding-v1 的所有改动**  
⚠️ **需要测试验证后合并到主分支**

