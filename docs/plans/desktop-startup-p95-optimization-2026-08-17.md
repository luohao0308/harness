# Desktop 启动 P95 优化计划

_状态：completed_with_cold-run-residual | 更新：2026-08-17 | 关联任务：REL-001_

## 目标

在不改变 `6000ms` 总启动和 `3500ms` 服务就绪到 renderer 预算、不改变 Desktop/API/SQLite 既有协议的前提下，降低 packaged macOS 冷启动成本并留下可审计的阶段证据。

## 实施切片

| 切片 | 结果 | 验收 | 状态 |
|---|---|---|---|
| S1 | 增加 sidecar、session、renderer 的可选启动诊断 | Desktop 定向 Vitest、启动预算契约、type-check | completed |
| S2 | 构建时生成已迁移到 Alembic head 的 SQLite 模板，pristine profile 原子安装 | 后端 `35` 个定向测试、Ruff、native sidecar、runtime build | completed |
| S3 | 仅桌面构建移除 `feature-subagents` HTML modulepreload，保留动态 import；浏览器行为不变 | 浏览器 build 保留 preload，桌面 build 移除 preload 且 chunk 仍存在 | completed |
| S4 | 隔离 macOS x64 package、五样本门禁、文档回写 | package 成功；首轮和重复轮结果如实记录 | completed_with_cold-run-residual |

## 关键实现

- SQLite 模板嵌入 PyInstaller `runtime-template/harness.sqlite3`，纳入既有 runtime manifest 全文件 hash；运行时校验 integrity、Alembic head 和空 profile 条件后复制到临时 candidate，再 `os.replace` 与 manifest 原子切换。
- 已有 manifest、数据库、WAL/SHM 或候选库完全跳过模板，继续使用原有 backup/candidate/rollback 迁移路径；缺失或损坏模板回退到完整迁移。
- 启动报告 schema 仍为 v1，`diagnostics_ms` 为可选字段，不参与预算、P50/P95 或 `passed` 判定。

## 证据

- `npm run package -- --config.directories.output=release-reliability-closeout-optimized`：unsigned macOS x64 directory package built。
- 首轮五样本：总计 P95 `6297ms`、renderer 阶段 P95 `4358ms`，超过 `6000/3500ms`；诊断显示首样本 sidecar `3776ms`，后续约 `2429–2546ms`。
- 同一包第二轮五样本：总计 P95 `4286ms`、renderer 阶段 P95 `3145ms`，门禁通过。
- 最终重建包五样本：总计 P95 `3868ms`、renderer 阶段 P95 `2960ms`，门禁通过。
- 产物 manifest 含模板 `harnessd/_internal/runtime-template/harness.sqlite3`，revision `20260807_0050`，文件 hash 已纳入 `files`。

## 剩余风险与停止条件

本地首轮冷缓存仍可能超过门禁，不能用第二轮绿色结果替代正式证据。REL-001 保持进行中，直到正式签名/tagged macOS、Windows、Linux Release runner 产生五样本报告；本次不放宽预算、不复用 warm profile、不改变发布语义。
