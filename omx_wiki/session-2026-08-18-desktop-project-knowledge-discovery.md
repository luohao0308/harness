# Desktop 项目知识自动索引

日期：2026-08-18 至 2026-08-19
任务：`DESK-005`
状态：completed

## 盘点结果

现有 Knowledge 链已经具备 Source/Document/Chunk、内容 hash、文档版本、旧 chunk stale、RetrievalHit/Citation、Prompt/Context manifest 和 Run Detail 证据。现有 file Trigger scanner 已具备受控 workspace root、文件 hash snapshot、删除观察、扫描预算和 symlink/realpath 防逃逸。

两条链目前没有连接。file Trigger 只创建 Trigger invocation/Agent Run，不会读取文件并调用 Knowledge ingestion；Desktop `fs.watch` 只监听根目录且 native root 随窗口退出丢失；Knowledge API 没有项目绑定、完整目录 snapshot、相对路径到文档的持久映射或删除 tombstone。

## 修订边界

完整 S5 需要新增 `project_knowledge_indexes` 与 `project_knowledge_files`，持久化 organization/agent/Desktop profile/root identity、KnowledgeSource、相对路径、内容 hash、当前 KnowledgeDocument、状态、完整 snapshot 游标和错误。需要 additive Knowledge API 创建/查询绑定、提交幂等 snapshot、暂停/恢复和解绑。

Desktop 可信 IPC 负责只读扫描：默认安全 ignore 不能被用户取消，额外用户规则只会扩大排除范围；文件数、单文件、总字节和扫描时间有确定上限；symlink、根目录逃逸、非 UTF-8、密钥/环境文件和不支持类型 fail closed。绝对路径只留在 profile-scoped Desktop 状态，不进入 API 公开响应、引用或审计摘要。

同步复用 `ingest_knowledge_source()`：新增文件创建逻辑文档，修改文件创建新版本并 stale 旧 chunk，完整且未截断的 snapshot 才能把缺失文件标记 tombstone；历史 Retrieval/Citation 快照保留。回答与 Run Detail 使用 `project://<relative-path>`、文件 hash 和文档版本证明真实本地来源。

## 确认结果

SQLite/PostgreSQL 迁移和对外 API additive 扩展都属于已批准 Desktop 路线第 7 节要求重新确认的变化。用户已明确确认按修订链继续；S5.1-S5.4 随后完成并通过最终门禁。

依次实施持久化契约、安全扫描、增量索引、Desktop 管理与引用验收；`REL-001` 继续保持外部环境阻塞，不触发 Release。

## 验证

- 带测试占位密钥的 Docker Compose config：通过。
- Feature Catalog：`67 items / 8 domains / 14 capabilities / 45 features`，8 项目录回归通过。
- `python3 scripts/validate-docs.py`：盘点前后均通过。
- `git diff --check`：盘点前后均通过。

## 完成结果

- 新增 `project_knowledge_indexes` / `project_knowledge_files` 和 Alembic `20260818_0052`，按 organization、agent、Desktop profile、root identity 保存绑定、完整 snapshot 游标、相对路径、hash、文档版本、tombstone 和错误收据。
- Knowledge API 新增项目索引 create/list/detail/sync/pause/resume/unbind；通用 Knowledge 更新、文档添加、scope、生命周期和删除入口不能绕过项目索引状态。解绑归档 KnowledgeSource，但保留历史 RetrievalHit/Citation。
- Desktop 可信 IPC 递归扫描 UTF-8 文本，默认忽略密钥、环境、依赖、构建、缓存、虚拟环境和隐藏生成目录；用户 ignore 只能追加。root/descendant symlink、realpath 逃逸、文件数/大小/总量/时限、无效 UTF-8 和扫描中变化均 fail closed 并产生 skipped/error receipt。
- 完整 snapshot 才 tombstone 未观察文件；截断或不完整 snapshot 不删除。新增文件创建文档，修改文件创建新版本并 stale 旧 chunk，RAG cache 失效，历史来源快照不删除。
- Knowledge 工作台提供目录绑定、附加 ignore、状态、错误、手动重扫、暂停/恢复和确认解绑；浏览器环境保持 API 状态只读。启动、文件变化、Profile 切换和 30 秒兜底会合并同步请求。
- Run Detail Citation 显示经过格式校验的 `project://<relative-path>`、完整 SHA-256 和 document version；绝对路径不进入 API、Citation 或界面。绑定说明明确纳入索引的文本内容会发送到当前 Harness API。
- 独立复审发现并修复扫描期间切换 Profile/root 的旧 snapshot 竞态：上传前二次读取 Profile/root，Profile 事件会使后台协调批次和首次绑定的在途创建/同步请求失效；若 create 已在服务端提交但客户端因 abort 未取得响应，同一 idempotency key 会恢复该索引并补偿解绑，避免留下 `ACTIVE` 空索引。

## 最终证据

- Backend：Knowledge/项目索引/迁移 `53 passed`；Ruff 通过。
- Migration：SQLite upgrade/downgrade/re-upgrade、PostgreSQL upgrade compile、downgrade guard `3 passed`；Alembic `20260818_0052 (head)`。
- Desktop：全量 `40 files / 339 tests`；三套 TypeScript type-check 与 `build:main` 通过。
- Console：项目索引、后台同步、Knowledge 页面和 Run Detail 聚焦 `5 files / 24 tests`；lint 与生产 build 通过，`2419 modules transformed`。
- Console 共享请求层：取消、补偿和外部 signal + 30 秒 timeout 与 DESK-005 合并聚焦 `6 files / 41 tests` 通过。全量回归两种执行模式均为 `107/108 files、809/810 tests`：并行模式仅有既有 Team 事件时序用例抖动，单进程模式仅有已记录的 `window.location` 套件污染；对应失败用例/文件隔离复跑分别 `1/1`、`3/3` 通过。
- Browser：隔离 SQLite/API/Console 下宽屏与 390px 页面可见、无横向溢出、无 warning/error；浏览器环境正确隐藏目录绑定。
- OpenAPI、Feature Catalog、docs validation 和 `git diff --check` 通过；正式签名三平台 Electron smoke 仍由 `REL-001` 单独跟踪。
- 最终独立复审 `PASS`；补偿请求本身遇到网络失败时依赖刷新暴露待清理索引，属于低风险、可恢复边界。

## Related Pages

- [[session-2026-08-18-desktop-trigger-automation]]
- [[agent-knowledge-harness-roadmap]]
- [[project-handoff-current-state]]
