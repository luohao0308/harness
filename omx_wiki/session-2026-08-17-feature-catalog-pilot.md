---
category: session-log
date: 2026-08-17
status: completed
task_id: FCAT-001
tags: [feature-catalog, agent-context, docs, dev-workflow]
---

# Feature Catalog 试点

## 目标

把 Harness 的功能、代码入口、规格、测试证据、实现状态、生产成熟度和已知缺口串成一个 AI 可查询的仓库级目录，并保持与现有 dev-workflow 文档职责边界一致。

## 交付

- `docs/development/ai/feature-catalog.json`：功能目录权威数据，使用 domain → capability → feature 三级层级。
- `docs/development/ai/feature-catalog.schema.json`：目录公共结构和枚举契约。
- `scripts/feature_catalog.py`：标准库校验、查询、矩阵生成和漂移检查。
- `docs/FEATURE-MATRIX.md`：从目录确定性生成的人类视图。
- `scripts/agent-context-brief.py`：任务 brief 输出高分功能及其成熟度、代码/规格/测试入口和缺口。
- `docs/development/ai/context-index.json`：`feature-catalog` 任务路由。
- Docs 校验：`validate-docs.py` 直接执行 catalog validate/check 和回归测试；`check-docs.sh` 保留详细回归入口。

首版目录覆盖 8 个领域、14 个能力和 41 个具体功能。当前具体功能为 40 个 `verified`、1 个 `in_progress`；成熟度最高为 `production_candidate`，没有条目声称 `production_proven`。

## 关键决策

- 试点使用 JSON + JSON Schema，不新增 YAML 解析依赖；现有 Docs CI 继续由标准库 Python 运行。
- 实现状态与生产成熟度分离：`verified` 不等同于 `production_ready`。
- Task Board 只记录当前工作，Feature Catalog 记录全量产品能力；两者不互相复制。
- 查询优先返回具体命中，再补充必要父级；平台词、英文停用词和单词内部子串不会制造弱匹配。

## 验证证据

- `python3 -m py_compile scripts/feature_catalog.py scripts/test_feature_catalog.py scripts/agent-context-brief.py scripts/validate-docs.py`：通过。
- `python3 scripts/feature_catalog.py --validate`：63 items / 8 domains / 14 capabilities / 41 features。
- `python3 scripts/feature_catalog.py --generate && python3 scripts/feature_catalog.py --check`：通过，矩阵确定性且无漂移。
- `python3 -m unittest scripts.test_feature_catalog -v`：8 passed。
- RAG、Groundedness、Desktop startup P95、Team task graph brief fixtures：通过，具体 feature 命中且无指定无关条目。
- `python3 scripts/validate-docs.py`：通过。
- `bash scripts/check-docs.sh`：通过；Markdown links 351 files / 520 local links。
- `git diff --check`：通过。

## 边界与后续

- 未修改产品运行时代码、API、数据库、部署行为或 dev-workflow 分发仓库。
- `REL-001` 的 Desktop 三平台正式 Release runner 证据和 `OPS-001` 的 Tempo/Loki 关联验证仍保持开放；目录反映这些缺口，没有升级成熟度声明。
- 后续如需抽离到 dev-workflow，应先基于本试点的字段、校验和 brief 命中反馈提炼通用 Schema/流程包；本页不把抽离视为已完成。
