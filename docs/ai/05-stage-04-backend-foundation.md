# 05 阶段 04：FastAPI 后端基础

## 阶段目标

初始化 Python 3.11 + FastAPI 后端，建立配置、日志、数据库连接、健康检查、OpenAPI 和基础测试。

## Required Context

- [执行协议](./00-execution-protocol.md)
- [任务进度说明](./01-task-progress.md)
- [机器可读任务进度](./task-progress.yaml)
- [架构与技术决策](./reference/architecture-and-decisions.md)

## AI 执行提示词

```text
你是本项目的后端工程执行 Agent。现在执行阶段 04：FastAPI 后端基础。

必须先读取 docs/ai/00-execution-protocol.md、docs/ai/01-task-progress.md、docs/ai/task-progress.yaml 和 docs/ai/reference/architecture-and-decisions.md。
只执行阶段 04，不进入阶段 05。
阶段开始前必须创建阶段分支，验证通过后 commit、push 并创建 PR。

执行内容：
1. 在 services/api-server 创建 pyproject.toml。
2. 固定 Python 版本为 3.11。
3. 安装依赖：fastapi、uvicorn、pydantic-settings、sqlalchemy、alembic、psycopg[binary]、redis、dramatiq、docker、prometheus-client、opentelemetry-api、opentelemetry-sdk、pytest、httpx、ruff。
4. 创建 app/main.py，提供 FastAPI 实例。
5. 创建 app/core/config.py，使用 pydantic-settings 读取环境变量。
6. 创建 app/core/logging.py，输出 JSON 日志。
7. 创建 app/db/session.py，建立 SQLAlchemy engine 和 session。
8. 创建 app/api/health.py，提供 GET /health。
9. 创建 tests/test_health.py。
10. 执行 pytest。
11. 更新 docs/ai/task-progress.yaml，把 stage-04-backend-foundation 标记为 completed。

PR 与进度要求：
- 阶段分支必须推送到 origin。
- 阶段变更必须创建 Pull Request。
- branch、commit_sha、pr_url 写入 docs/ai/task-progress.yaml。
- 人读进度 docs/human/10-task-progress.md 必须同步更新。

验收标准：
- GET /health 返回 ok。
- pytest 通过。
- FastAPI OpenAPI 可生成。
- JSON 日志模块存在。
- 数据库 session 模块存在。
- task-progress.yaml 已更新。
```

## Required Structure

```text
services/api-server/
├─ pyproject.toml
├─ app/
│  ├─ main.py
│  ├─ api/
│  │  └─ health.py
│  ├─ core/
│  │  ├─ config.py
│  │  └─ logging.py
│  └─ db/
│     └─ session.py
└─ tests/
   └─ test_health.py
```

## Required Health Response

```json
{
  "status": "ok",
  "service": "api-server"
}
```

## Verification Commands

```bash
cd services/api-server
python -m pytest
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health
```

## Progress Update Rule

```yaml
stage-04-backend-foundation:
  status: completed
  verification_result: passed
  next_stage: stage-05-task-event-store
```

