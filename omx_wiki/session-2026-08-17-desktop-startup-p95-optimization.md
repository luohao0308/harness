# Desktop 启动 P95 优化

Category: `delivery`

Tags: `desktop`, `startup`, `sqlite`, `packaging`, `performance`

## Outcome

完成四个优化切片：启动链路可观测、packaged sidecar 使用预迁移 SQLite 模板、桌面首屏不再预加载非首屏 subagents chunk，并完成隔离 macOS x64 package 与五样本复核。预算保持 `6000ms/3500ms` 不变。

## Changes

- `diagnostics_ms` 记录 sidecar spawn/ready、Desktop session、renderer load 起止和派生耗时；旧启动报告仍兼容。
- build-harnessd 生成当前 Alembic head 的空 SQLite 模板并随 bundle hash 校验；只对 pristine profile 原子安装，已有库和异常回退沿用原 candidate migration。
- Vite 桌面构建通过 `modulePreload.resolveDependencies` 过滤 `feature-subagents`，浏览器构建保持原 preload，动态路由 chunk 仍保留。

## Evidence

- 后端定向测试 `35 passed`，Ruff passed；native harnessd integration passed。
- `npm run package -- --config.directories.output=release-reliability-closeout-optimized` passed；manifest 包含模板，revision `20260807_0050`。
- 优化包首轮五样本仍被冷缓存波动阻断：总计 P95 `6297ms`、renderer P95 `4358ms`。
- 同一包第二轮通过：总计 P95 `4286ms`、renderer P95 `3145ms`。
- 最终重建包首轮通过：总计 P95 `3868ms`、renderer P95 `2960ms`。

## Handoff

REL-001 仍是正式 Release runner 证据项。不要调整预算、复用 warm profile 或把第二轮结果当成首轮冷启动保证；后续应在签名/tagged macOS/Windows/Linux runner 上复核，并继续关注首样本 sidecar 冷启动波动。
