# 10 阶段 09：Docker Sandbox 与 WarmPool

## 阶段目标

实现 Docker 容器级沙箱执行、Shell 工具隔离、资源限制、命令超时、WarmPool 预热容器池和相关事件指标。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [架构与技术决策](./reference/architecture-and-decisions.md)
- [运行时与部署规格](./reference/runtime-deployment-spec.md)
- [数据、事件与 API](./reference/data-events-api.md)

## AI 执行提示词

```text
你是本项目的运行时执行 Agent。现在执行阶段 09：Docker Sandbox 与 WarmPool。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml、docs/ai/reference/architecture-and-decisions.md、docs/ai/reference/runtime-deployment-spec.md 和 docs/ai/reference/data-events-api.md。
只执行阶段 09，不进入阶段 10。
阶段开始前必须创建阶段分支，验证通过后 commit、push 并创建 PR。

执行内容：
1. 创建 app/sandbox/docker_manager.py。
2. 创建 app/sandbox/warm_pool.py。
3. 创建 app/sandbox/policies.py。
4. 创建 app/tools/shell.py。
5. shell 工具必须通过 Docker SDK 执行命令。
6. shell 工具禁止使用 subprocess 在宿主机执行 Agent 命令。
7. 容器默认 memory=1024m、cpus=1.0、network=none、user=non-root。
8. 每条命令必须有 timeout。
9. 捕获 stdout、stderr、exit_code、duration_ms。
10. 写入 SANDBOX_REQUESTED、SANDBOX_ALLOCATED、SANDBOX_COMMAND_STARTED、SANDBOX_COMMAND_COMPLETED、SANDBOX_COMMAND_FAILED、SANDBOX_RELEASED、SANDBOX_DESTROYED。
11. WarmPool 固定 MIN_SIZE=3、MAX_SIZE=10、IDLE_TTL_SECONDS=600。
12. WarmPool 命中写入 SANDBOX_REUSED_FROM_WARM_POOL。
13. GET /api/sandboxes、GET /api/sandboxes/{sandbox_id}、GET /api/sandboxes/warm-pool、POST /api/sandboxes/{sandbox_id}/terminate 必须存在。
14. 创建测试覆盖 DockerManager 参数、Shell 工具走 Docker、WarmPool acquire/release。
15. 更新 docs/ai/task-progress.yaml，把 stage-09-sandbox-warmpool 标记为 completed。

PR 与进度要求：
- 阶段分支必须推送到 origin。
- 阶段变更必须创建 Pull Request。
- branch、commit_sha、pr_url 写入 docs/ai/task-progress.yaml。
- 人读进度 docs/human/10-task-progress.md 必须同步更新。

验收标准：
- DockerManager 存在。
- WarmPoolManager 存在。
- shell 工具不使用宿主机 subprocess。
- 沙箱事件完整写入。
- WarmPool 指标接口存在。
- pytest 通过。
- task-progress.yaml 已更新。
```

## Required Files

```text
services/api-server/app/sandbox/docker_manager.py
services/api-server/app/sandbox/warm_pool.py
services/api-server/app/sandbox/policies.py
services/api-server/app/tools/shell.py
services/api-server/app/api/sandboxes.py
services/api-server/tests/test_sandbox.py
services/api-server/tests/test_warm_pool.py
```

## Required Container Defaults

```yaml
image: agent-runtime:latest
memory: 1024m
cpus: "1.0"
network: none
user: non-root
workspace_mount: /workspace
command_timeout_required: true
```

## Verification Commands

```bash
cd services/api-server
python -m pytest
rg -n "subprocess" app/tools app/sandbox
curl http://127.0.0.1:8000/api/sandboxes/warm-pool
```

`rg -n "subprocess" app/tools app/sandbox` 必须没有 Agent shell 执行路径。

## Progress Update Rule

```yaml
stage-09-sandbox-warmpool:
  status: completed
  verification_result: passed
  next_stage: stage-10-observability-deployment
```

