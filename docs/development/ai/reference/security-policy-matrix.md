# Security Policy Matrix

本文件定义角色、权限、工具、安全策略、审计要求和脱敏规则。

## Roles

```text
owner
admin
engineer
viewer
auditor
service_account
```

## Permission Matrix

| action | owner | admin | engineer | viewer | auditor | service_account |
|---|---|---|---|---|---|---|
| create_task | allow | allow | allow | deny | deny | allow |
| start_task | allow | allow | allow | deny | deny | allow |
| cancel_task | allow | allow | allow_own | deny | deny | allow_own |
| resume_task | allow | allow | allow_own | deny | deny | allow_own |
| view_task | allow | allow | allow_project | allow_project | allow | allow_project |
| view_events | allow | allow | allow_project | allow_project | allow | allow_project |
| export_audit_log | allow | allow | deny | deny | allow | deny |
| manage_models | allow | allow | deny | deny | deny | deny |
| manage_policies | allow | allow | deny | deny | deny | deny |
| enable_network | allow | allow | deny | deny | deny | deny |
| run_shell | allow | allow | allow_project | deny | deny | deny |
| access_secrets | allow | allow | deny | deny | deny | deny |
| terminate_sandbox | allow | allow | allow_own | deny | deny | deny |

## Tool Policy Matrix

| tool | risk | sandbox | network | roles | audit |
|---|---|---|---|---|---|
| read_file | low | false | none | admin, engineer | standard |
| list_files | low | false | none | admin, engineer | standard |
| write_file | high | true | none | admin, engineer | elevated |
| run_shell | high | true | none | admin, engineer | elevated |
| run_tests | high | true | none | admin, engineer | elevated |
| install_package | high | true | restricted | admin | critical |
| network_request | high | true | restricted | admin | critical |
| git_command | high | true | restricted | admin, engineer | elevated |
| secret_read | critical | true | none | owner, admin | critical |

## Runtime Settings Binding

```text
settings_key: settings.policies
runtime_reader: PolicyEngine
decision_consumer: ToolRunner
effective_fields: risk_levels, approvals, sandbox, audit
sandbox_consumer: DockerManager, WarmPoolManager
sandbox_effective_fields: default_network, default_timeout_seconds, memory_mb, cpus, workspace_quota_mb, network_allowlist
```

## Sandbox Policy

```yaml
default_network: none
default_memory: 1024m
default_cpus: "1.0"
default_workspace_quota_mb: 1024
network_allowlist: []
default_user: non-root
workspace_scope: task
command_timeout_required: true
write_scope: /workspace/output
tmp_scope: /workspace/tmp
```

## Audit Requirements

The following actions must emit audit events:

```text
create_task
start_task
cancel_task
resume_task
tool_call
policy_check
policy_denied
secret_access
sandbox_create
sandbox_destroy
model_call
audit_export
settings_change
```

## Redaction Rules

Never log:

```text
raw_api_key
secret_value
full_prompt
raw_sensitive_file_content
authorization_header
cookie_header
private_key
database_password
```

Log summaries:

```text
prompt_hash
prompt_token_count
file_path
file_size
stdout_preview
stderr_preview
secret_reference_id
```

## Policy Decision Shape

```json
{
  "allowed": false,
  "reason": "network access requires admin role",
  "policy_id": "network-admin-only",
  "audit_level": "critical"
}
```

## Required Events

Policy allow:

```text
POLICY_CHECKED
```

Policy deny:

```text
POLICY_CHECKED
POLICY_DENIED
TOOL_DENIED_BY_POLICY
```

Secret access:

```text
SECRET_ACCESSED
```
