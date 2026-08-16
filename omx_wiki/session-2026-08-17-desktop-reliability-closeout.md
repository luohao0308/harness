# Desktop 可靠性交付收口

Category: `delivery`

Tags: `desktop`, `console`, `routes`, `typescript`, `release`, `startup`, `ci`

## Outcome

Desktop 可靠性交付四阶段已完成：旧 Console URL 可兼容跳转，Desktop 严格类型检查恢复，Release CI 对三平台启动报告增加独立跨工件校验，完整本地回归和文档门禁通过。

## Implementation

- `/settings/data` 重定向到 `/settings/data-management`，保留 query/hash；`/subagents/specialists` 及详情路径重定向到 `/subagent-specialists`，并在动态 `/subagents/:subagentId` 之前注册静态兼容路由。
- Desktop `type-check` 拆分为主进程、浏览器适配器和测试三个 TypeScript 项目，仍保持 `strict: true`；同时修复真实 fixture/mock 类型漂移和一个 `TaskStore.query` 接口默认参数不一致。
- Release CI 新增 `desktop-startup-evidence` job，下载 `harness-desktop-*` 工件时保持目录隔离，校验平台/架构、报告唯一性、五样本数量、聚合字段、P95 通过状态和共享 app version，然后生成 `desktop-startup-evidence.json`。
- `github-release` 同时依赖平台构建和独立证据 job；三份原始报告与汇总证据一起进入 Release asset。没有改变 API、数据库、签名或发布 tag 语义。

## Evidence

- Console 路由单测：`2 files / 13 tests passed`。
- Console 企业 Chromium 路由冒烟：`44 passed`，包含新增专家旧详情入口；lint/build 通过，构建转换 `2414` modules。
- Desktop：严格 `npm run type-check`、`build:main` 通过；全量 `38 files / 324 tests passed`。
- Startup/Release：`npm run test:startup-budget` `10 passed`；新增 Node 脚本语法、Release workflow 静态契约和系统 Ruby YAML 解析通过。
- 文档：`validate-docs.py`、Markdown 链接检查和 `git diff --check` 通过。

## Delivery

- `8218d32 docs(plan): define desktop reliability closeout`
- `7c6d516 fix(console): restore legacy settings and specialist routes`
- `d2dcfc6 fix(desktop): restore strict type-check boundaries`
- `75880da ci(release): validate desktop startup evidence`
- S4 文档、任务状态和交接回写随最终交付提交完成。

## Remaining Risk

`REL-001` 仍保留为外部证据项：真实 macOS、Windows、Linux Release runner 的五样本 P95 数值必须由未来正式 tag 运行产生。本地 Node/Chromium/类型检查只能证明契约和门禁逻辑，不能替代真实跨平台打包测量。生产签名、公证和 Release tag 也未在本次任务中触发。
