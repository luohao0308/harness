---
category: session-log
date: 2026-08-17
status: completed
task_id: FCAT-002
tags: [feature-catalog, dev-workflow, optional-pack, extraction]
---

# Feature Catalog dev-workflow 提取

## 目标

把 Harness 中已验证的 Feature Catalog 试点提炼为通用、可选的 dev-workflow 流程包，同时保持功能事实、代码路径、测试证据、成熟度和生成矩阵属于使用该流程的目标项目。

## 通用交付

- `feature-catalog` 是独立可选包，不改变 Core-only 或其他流程包的行为。
- 包内提供 JSON Schema、初始化模板、字段/成熟度说明和仅依赖 Python 3 标准库的 CLI。
- CLI 支持 `--init`、`--validate`、`--generate`、`--check`、`--query`，以及根目录、文件路径和查询过滤参数。
- 平台使用目标项目自定义的小写标签；`not_started` / `in_progress` 功能可诚实记录尚无测试或证据，`verified` 和生产成熟度仍受证据门约束。
- Bash/PowerShell 审计在安装该包时调用目标项目工具执行 `--check`；pending/blocked 状态记告警，ready 状态记错误。
- 集成回归覆盖安装、初始化、重装、矩阵漂移、部分卸载和完整卸载，并证明活动清单和矩阵持续保留。
- dev-workflow 版本从确认的 `0.2.1` 基线提升到 `0.3.0`，manifest schema 保持 `2`。

## 项目边界

- Harness 继续以 `docs/development/ai/feature-catalog.json` 为项目功能事实权威，以 `docs/FEATURE-MATRIX.md` 为生成视图。
- Harness 的 63 项目录、项目 Schema、task-aware brief、Docs CI 门禁和 `scripts/feature_catalog.py` 定制实现没有被通用包替换。
- 通用包只管理 Schema、模板、说明和工具；目标项目初始化产生的活动清单与矩阵不进入 manifest 文件所有权，卸载时保留。
- 没有把 Harness 的业务条目、路径、任务 ID、数量断言或成熟度结论写入 dev-workflow 模板。

## 验证证据

- JSON Schema 和模板通过 `python3 -m json.tool`。
- Python 工具与测试通过 `py_compile`。
- `python3 -m unittest tests.test_feature_catalog -v`：13 passed。
- `LC_ALL=C LANG=C bash tests/integration.sh`：通过。
- Bash 安装、审计、卸载和集成脚本通过 `bash -n`。
- `git diff --check`：通过。
- 本机没有 `pwsh`，PowerShell 审计和集成测试代码已同步实现，但未在此环境执行。

## 交付状态

实现保留在 dev-workflow 的 `codex/feature-catalog-pack` 分支工作树中。按用户范围没有 commit、tag、push、release，也没有把未发布的 `0.3.0` 重新安装进 Harness。
