# Desktop 原生变更审查工作区

日期：2026-08-17
任务：`DESK-003`
状态：completed

## 结果

Desktop 新增 `/changes` 原生变更审查工作区。用户可在当前受控工作区查看 Git 状态、已暂存与工作区 Diff，并通过显式确认执行分块 stage、unstage 或 revert。未跟踪文本文件使用整文件暂存语义，二进制、冲突、过大 Diff 和 Git 故障保持只读结果。

## 安全边界

- Git 通过固定参数数组执行，不经过 shell，不接受 renderer 提供的 Git flags。
- workspace 必须是仓库根目录；绝对路径、目录逃逸和 symlink 被拒绝。
- 写操作要求 opaque preview token、过期检查、文件状态和 patch identity 复核。
- mutation 前后写入组织隔离的服务器审计；只有 Admin/Engineer 可写，完成审计失败时回滚 Git mutation。
- 不使用 reset、clean、checkout、force 或隐式删除；未跟踪文件只有显式 revert 才删除。

## 验证

- Desktop：`40 files / 337 tests`，`npm run type-check`、`npm run build:main` 通过。
- Console：`/changes`、路由和壳层 `4 files / 40 tests`，lint、2416-module production build 通过。
- API：change-review audit 与 attention `22 passed`，Ruff 通过；组织隔离、角色、引用一致性、请求校验和跨阶段 operation identity 有覆盖。
- OpenAPI：参考、主 JSON/YAML 和官网 JSON/YAML 的 change-review 子契约语义哈希一致。
- 浏览器：宽屏与窄屏 Desktop-only fallback 可见，无 document 级横向溢出；真实本地能力由 Electron IPC 回归覆盖。

## 剩余风险

正式签名 macOS/Windows/Linux 包内 smoke 仍依赖 `REL-001` 的 Release runner。`operation_id + phase` 并发幂等目前为应用层查重，未引入数据库唯一约束；当前请求使用随机 UUID 且顺序写入，后续涉及 Schema 的切片再评估持久化约束。

路线已自动推进到 `DESK-004`，`REL-001` 保持暂停/阻塞，不视为完成。
