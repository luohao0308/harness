---
workflow: dev-workflow
status: ready
updated: 2026-08-11
---

# dev-workflow 接入记录

> 本文件记录当前项目是否已经完成通用开发流程接入。它不是任务状态源，也不是项目稳定事实源；任务状态看 `TASKS.md`，稳定事实看 `PROJECT-SUMMARY.md`。

## 状态说明

- `pending`：模板已安装，但项目画像、命令、所有权或流程包映射仍未完成。
- `ready`：项目画像已根据代码和运行证据完成，后续任务可以按本流程直接执行。
- `blocked`：接入被缺少权限、运行环境或无法验证的关键事实阻塞。

机器可读的安装版本、流程包、接入状态和最近一次已记录审计时间保存在 `.dev-workflow/manifest.json`。该文件不应包含凭据、绝对本机路径或动态生产秘密。

## 首次接入步骤

1. 只读扫描仓库拓扑、子仓库、模块所有权、入口和本地运行方式。
2. 从仓库脚本、配置和 CI 中确认安装、启动、测试、lint、类型检查、构建、迁移和发布入口。
3. 找出已有架构、设计、契约、测试、运维和工作日志文档，建立职责映射；不要因为模板路径不同就复制第二套权威文档。
4. 识别受保护路径、凭据边界、需要人工授权的操作和无法验证的 Unknown。
5. 将已验证稳定事实填入 `PROJECT-SUMMARY.md`，将项目专属规则填入根 `AGENTS.md` 的项目扩展区或现有等价入口。
6. 按实际启用的流程包补充导航、命令矩阵、契约索引、Runbook 和验证入口。
7. 保持 `pending` 状态运行接入审计；预期退出码为 `2`，但不应有结构错误，告警应逐项处理或解释。
8. 完成检查清单后，同步将本文件与 manifest 的 `onboarding.status` 改为 `ready`，在 manifest 写入 UTC `lastAuditAt`，再运行审计并确认退出码为 `0`。

## 接入检查清单

- [x] 仓库拓扑和每个路径的所有权已确认。
- [x] 真实开发、测试、构建和 CI 命令已记录。
- [x] 项目摘要、路径速查和项目专属规则已填充。
- [x] 已有文档与新流程包已建立职责映射，没有并行权威源。
- [x] 契约、迁移、发布、健康检查和回滚入口按项目适用性登记。
- [x] 敏感信息和不可逆操作边界已明确。
- [x] Unknown、阻塞和需要人工确认的事项已记录。
- [x] 已从 dev-workflow 分发仓库运行 `audit.sh`；最终 `ready` 状态审计退出码为 `0`。

## 既有文档映射

| 通用职责 | 当前项目权威路径 | 是否已核验 | 备注 |
|---|---|---|---|
| 任务状态 | [`docs/development/ai/task-progress.yaml`](development/ai/task-progress.yaml)；当前板见 [`TASKS.md`](TASKS.md) | yes | YAML 是机器状态源，Task Board 只保留摘要 |
| 短期上下文 | [`WORKING-CONTEXT.md`](WORKING-CONTEXT.md) | yes | 当前接入任务已关闭，后续任务按需重建 |
| 稳定项目摘要 | [`PROJECT-SUMMARY.md`](PROJECT-SUMMARY.md) | yes | 入口、模块、命令和边界速查 |
| 架构/模块 | [`architecture/`](architecture/)、[`architecture/MODULE-INDEX.md`](architecture/MODULE-INDEX.md)、[`architecture/adr/`](architecture/adr/) | yes | 架构目录提供导航，ADR 原文保持权威 |
| 设计/计划 | [`DESIGN.md`](../DESIGN.md)、[`design/`](design/)、[`plans/`](plans/) | yes | 产品设计与实施计划分开维护 |
| 契约/生成物 | [`contracts/SPEC-INDEX.md`](contracts/SPEC-INDEX.md)、[`contracts/api/openapi.yaml`](contracts/api/openapi.yaml)、[`contracts/`](contracts/) | yes | OpenAPI 由脚本生成，事件/数据规格见既有文档 |
| 测试/验证 | [`testing/qa/test-strategy.md`](testing/qa/test-strategy.md)、[`testing/`](testing/)、CI workflows | yes | 定向门禁与发布门禁分层 |
| 运维/Runbook | [`project-memory/runbooks/`](project-memory/runbooks/)、[`operations/`](operations/)、[`project-memory/`](project-memory/) | yes | 部署、迁移、回滚、观测和排障入口 |
| 历史证据 | [`工作日志/`](工作日志/)、[`工作日志/reports/`](工作日志/reports/)、[`../omx_wiki/`](../omx_wiki/) | yes | 过程证据与跨会话交接，不覆盖当前实现 |

## 审计记录

| 时间 | 命令/入口 | 结果 | 证据/剩余风险 |
|---|---|---|---|
| 2026-08-10 | `feature/bash-3-array-compat/scripts/audit.sh --target <project> --strict` | ready | 提交 `a454fe0` 的 Bash 3.2 空数组兼容修复已拉取；结构、manifest、Core、五个流程包和 onboarding 状态通过。 |
| 2026-08-11 | Docs CI `bash scripts/check-docs.sh` + strict audit | ready | Docs CI 已强制运行结构与全仓 Markdown 本地链接门禁；`validate-docs.py` 同时校验 CI 契约，严格审计继续返回 `ready`。 |

_完成接入后保留本文件作为流程状态入口；不要把一次性排障过程复制到这里。_
