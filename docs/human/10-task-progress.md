# 10 任务进度看板

本文件是人读任务进度看板。机器事实源是 [task-progress.yaml](../ai/task-progress.yaml)。AI 每次完成阶段验证、提交、推送和创建 PR 后，必须同步更新本文件。

## 当前状态

```text
当前阶段：阶段 13 Website Code Integration
当前状态：ready_for_review
当前验证：passed
下一步：等待用户合并 PR #11
```

## 状态说明

```text
pending：未开始
in_progress：正在执行
ready_for_review：已验证、已提交、已推送、已创建 PR，等待用户合并
completed：PR 已合并，阶段完成
blocked：被外部条件阻塞
failed：验证失败
```

## 阶段进度

| 阶段 | 名称 | 状态 | 分支 | PR | 验证结果 | 说明 |
|---|---|---|---|---|---|---|
| 01 | GitHub 与 Git 初始化 | completed | legacy_no_pr | legacy_no_pr | passed | 历史补录阶段：Git 仓库、模板、工作流和忽略规则已建立。 |
| 02 | Figma 设计源 | completed | legacy_no_pr | legacy_no_pr | passed | 历史补录阶段：设计 brief、tokens、页面清单已建立。 |
| 03 | 仓库脚手架 | completed | legacy_no_pr | legacy_no_pr | passed | 历史补录阶段：Monorepo 目录、环境样例和检查脚本已建立。 |
| 04 | FastAPI 后端基础 | completed | stage/stage-04-backend-foundation | https://github.com/luohao0308/harness/pull/2 | passed | PR 已合并到 develop。 |
| 05 | Task 与 Event Store | completed | stage/stage-05-task-event-store | https://github.com/luohao0308/harness/pull/3 | passed | PR 已合并到 develop。 |
| 06 | Planner 与 Executor | completed | stage/stage-06-planner-executor | https://github.com/luohao0308/harness/pull/4 | passed | PR 已合并到 develop。 |
| 07 | React 控制台 | completed | stage/stage-07-react-console | https://github.com/luohao0308/harness/pull/5 | passed | PR 已合并到 develop。 |
| 08 | Dramatiq Subagent | completed | stage/stage-08-dramatiq-subagent | https://github.com/luohao0308/harness/pull/6 | passed | PR 已合并到 develop。 |
| 09 | Docker Sandbox 与 WarmPool | completed | stage/stage-09-sandbox-warmpool | https://github.com/luohao0308/harness/pull/7 | passed | PR 已合并到 develop。 |
| 10 | 监控、日志、部署 | completed | stage/stage-10-observability-deployment | https://github.com/luohao0308/harness/pull/8 | passed | PR 已合并到 develop。 |
| 11 | Review P1 Production Hardening | completed | stage/stage-11-review-p1-hardening | https://github.com/luohao0308/harness/pull/9 | passed | 5 个 P1 已修复；PR #9 已合并；Docker Compose、API、Nginx、SSE、WarmPool、前端浏览器、Prometheus、Grafana 均已通过验收；后续补充已将 Subagent、Sandbox、WarmPool、Observability 后端能力展示到控制台，并生成中文 OpenAPI JSON 导入镜像。 |
| 12 | Runtime Product Completion | completed | stage/stage-12-runtime-product-completion | https://github.com/luohao0308/harness/pull/10 | passed | 已补齐 task cancel/resume/result/replay、model_calls、tool_calls、filesystem/http tools、settings API、ADMIN_ACTION 审计、控制台 settings/replay/result/observability 页面、默认中文、中英文切换和中文 OpenAPI JSON/YAML。 |
| 13 | Website Code Integration | ready_for_review | stage/stage-13-website-code-integration | https://github.com/luohao0308/harness/pull/11 | passed | 已接收用户提供的官网前端代码，保留视觉结构，完成 Next.js 工程化、后端接入、控制台导流、OpenAPI 入口、文档入口、部署接入；本轮追加子 Agent 详情页、结果产物钻取、官网真实控制台深链和 Spec 覆盖同步。 |

## 阶段完成定义

阶段进入 `ready_for_review` 必须满足：

```text
阶段任务完成
Verification Commands 通过
变更已 commit
阶段分支已 push 到 origin
Pull Request 已创建
task-progress.yaml 已更新
本看板已更新
```

阶段进入 `completed` 必须满足：

```text
用户已合并 PR
develop 已包含阶段变更
task-progress.yaml 的 merged_at 已填写
本看板状态已更新
```

## 当前 Docker 验收结果

```text
API: http://127.0.0.1:8000/health passed
Website: http://127.0.0.1:3000 passed
Console: http://127.0.0.1:5173/tasks passed
Nginx: http://127.0.0.1:8080/health passed
Nginx SSE: /api/tasks/{task_id}/events/stream passed
Prometheus: http://127.0.0.1:9091/-/healthy passed
Grafana: http://127.0.0.1:3001/api/health passed
WarmPool: idle=3 passed
Browser console: zero error or warning logs
```

## 历史补录说明

阶段 01-03 在 PR 规则建立前已经完成，使用 `legacy_no_pr` 标记。阶段 04 及之后必须走阶段分支、提交、推送、PR、用户合并流程。阶段 11 是阶段 10 完成后的 review 修复阶段，现已完成并合并。阶段 12 是基于原始产品与运行时文档的补齐阶段，必须在 PR #9 合并后启动。阶段 13 是用户提供官网代码后的接入阶段。
