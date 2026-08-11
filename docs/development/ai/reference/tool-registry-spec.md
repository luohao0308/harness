# Tool Registry Spec

本文件只保留工具治理规则。工具字段、工具列表、输入输出 schema 和角色配置以 [tool-registry.yaml](./tool-registry.yaml) 为唯一机器契约。

## Risk Rules

```text
low: read-only, no network, no file mutation
medium: read workspace files, generate reports, limited network metadata
high: shell command, file write, package install, test execution
critical: secret access, external deployment, destructive command, git push
```

## Mandatory Sandbox Rules

以下工具必须进入 Docker Sandbox：

```text
run_shell
run_tests
install_package
write_file
apply_patch
git_command
network_request
```

## Audit Events

每次工具调用必须写入：

```text
POLICY_CHECKED
TOOL_CALLED
TOOL_RESULT_RECEIVED
```

策略拒绝必须写入：

```text
POLICY_DENIED
TOOL_DENIED_BY_POLICY
```

超时必须写入：

```text
TOOL_TIMEOUT
```

## Implementation Ownership

```text
机器契约：docs/development/ai/reference/tool-registry.yaml
后端实现：services/api-server/app/tools/registry.py
执行入口：services/api-server/app/tools/runner.py
公开接口：POST /api/tasks/{task_id}/tools/execute
策略实现：services/api-server/app/sandbox/policies.py
审计实现：services/api-server/app/events/event_store.py
```

## Current Runtime Coverage

```text
read_file: real workspace read
list_files: real workspace listing
write_file: sandbox command path
run_shell: sandbox command path
run_tests: sandbox command path
network_request: sandbox command path, admin role only
git_command: sandbox command path
public_execute_api: task scoped tool execution with audit record
policy_denied: writes POLICY_CHECKED, POLICY_DENIED, TOOL_DENIED_BY_POLICY
policy_settings: risk level, approval, role and sandbox rules are read from system_settings
```
