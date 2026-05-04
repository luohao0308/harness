# Threat Model

本文件定义企业 AI Agent Harness 平台的安全威胁、控制措施、检测信号和验收要求。

## Scope

```text
API Server
Agent Harness Core
Planner
Executor
Subagent
Tool Registry
Policy Engine
Event Store
Docker Sandbox
WarmPool
Model Gateway
Frontend Console
Deployment Runtime
```

## Assets

```text
model_api_keys
task_inputs
task_outputs
event_streams
workspace_files
sandbox_containers
audit_logs
user_tokens
policy_config
deployment_secrets
```

## Trust Boundaries

```text
browser -> api-server
api-server -> database
api-server -> redis
executor -> tool-registry
tool-registry -> sandbox
sandbox -> docker-engine
model-gateway -> model-provider
worker -> redis
nginx -> api-server
```

## Threats And Controls

### Prompt Injection

Threat:

```text
User content instructs Agent to ignore policy, reveal secrets, bypass sandbox, or alter audit logs.
```

Controls:

```text
system prompt hierarchy
Tool Registry allowlist
Policy Engine enforcement
secret redaction
audit events
model input sanitization
```

Detection:

```text
POLICY_DENIED frequency
TOOL_DENIED_BY_POLICY frequency
secret access attempts
high-risk tool attempts
```

### Tool Abuse

Threat:

```text
Agent calls shell, network, package install, git command, or file mutation outside approved boundaries.
```

Controls:

```text
registered tools only
high-risk tools require Docker Sandbox
role-based tool access
per-tool timeout
workspace write scope
network default none
```

Detection:

```text
TOOL_CALLED by risk_level
POLICY_DENIED by tool_name
sandbox_command_timeout_total
unexpected network request attempts
```

### Sandbox Escape

Threat:

```text
Command executed inside container attempts host access, privilege escalation, Docker socket access, or filesystem escape.
```

Controls:

```text
non-root container user
limited mounts
network none by default
cpu and memory limits
no Docker socket mount inside sandbox
temporary workspace
container destroy on dirty state
```

Detection:

```text
sandbox command exit codes
kernel audit logs
container runtime errors
sandbox failed state
```

### Secret Leakage

Threat:

```text
Secrets appear in model prompts, logs, events, stdout, stderr, screenshots, or exported audit files.
```

Controls:

```text
secret reference IDs
redaction before logging
no full prompt logs
authorization header filtering
critical audit for secret access
```

Detection:

```text
secret scanner on logs
SECRET_ACCESSED events
raw_api_key pattern scan
private key pattern scan
```

### Event Log Tampering

Threat:

```text
Actor changes, deletes, reorders, or fabricates Event Store records.
```

Controls:

```text
append-only event table
unique task sequence
database role separation
audit export
event hash chain in enterprise edition
```

Detection:

```text
sequence gaps
duplicate sequence attempts
database permission audit
event replay mismatch
```

### WarmPool Residue

Threat:

```text
Data from one task remains in a reused warm container and becomes visible to another task.
```

Controls:

```text
workspace cleanup before release
dirty container destroy
environment reset
process cleanup
high-risk tasks use single-use containers
```

Detection:

```text
WarmPool cleanup test failure
unexpected file residue
container dirty marker
warm_pool_destroy_total
```

### Supply Chain Attack

Threat:

```text
Package install, base image, GitHub Actions dependency, or runtime image introduces malicious code.
```

Controls:

```text
pinned dependencies
locked package files
base image scan
restricted package install tool
GitHub branch protection
CI security checks
```

Detection:

```text
dependency audit findings
image scan findings
unexpected outbound network
package install events
```

## Required Security Tests

```text
prompt injection policy denial
shell command sandbox enforcement
network disabled by default
secret redaction in logs
event append-only enforcement
WarmPool cleanup isolation
RBAC denied actions
```

## Security Release Gate

Release requires:

```text
security policy matrix reviewed
threat model reviewed
sandbox tests passed
secret scan passed
event replay tests passed
RBAC tests passed
```

