# Desktop 本地会话续期实施计划

_状态：completed | 更新：2026-08-11 | 关联任务：desktop-local-session-renewal-2026-08-11 | 关联设计：[Desktop 本地运行时计划](../../.omx/plans/desktop-local-runtime-sqlite-install-ready.md)_

## 1. 目标、成功标准与停止条件

- 目标结果：Desktop 长时间运行或系统睡眠恢复后继续使用内置 `harnessd`，不因本地 Cookie 的 60 分钟 JWT 过期显示 401。
- 可验收成功标准：主进程主动续期；本地请求遇到 401 时经受信 IPC 单飞续期并自动重试；真实模型调用仍使用安全存储中的配置。
- 完成后停止条件：定向测试、Desktop/Console 构建、打包应用真实冒烟与文档校验通过，应用保持运行。

## 2. 范围与非范围

### 范围

- Electron `LocalRuntimeManager` 的 Cookie 续期、停止和运行时重启生命周期。
- Desktop preload/IPC 的受信会话续期入口。
- 本地 profile 的 API 401 自动续期重试。
- 从“面试 Web”配置到 Desktop safeStorage 的不回显迁移和真实调用验证。

### 非范围

- 不延长企业 Web 登录或 API Bearer Token 的全局有效期。
- 不改变 Web 扩展单次 bootstrap 的来源绑定、一次性消费和 HttpOnly Cookie 边界。
- 不读取、记录或输出模型 API Key 明文。

## 3. 当前证据基线

- Desktop 只在启动或 `harnessd` 重启时调用 `/api/local-runtime/desktop-session`。
- 本地 Cookie 使用普通 access JWT，默认 60 分钟过期；当前应用运行约 3.5 小时后真实出现 `HTTP 401 Bearer token 无效`。
- 同一模型配置此前完成真实 Run，说明截图中的失败不是模型 provider 鉴权失败。

## 4. 原则与决策

| 决策 | 选择 | 理由 | 代价 |
|---|---|---|---|
| 续期所有者 | Electron 主进程 | bootstrap secret 不进入 renderer | 增加 timer/IPC 生命周期 |
| 失败恢复 | 主动续期 + 401 单次重试 | 覆盖长时间运行、睡眠和竞态 | 需要跨 Desktop/Console 测试 |
| Web 扩展 | 保持现状 | 不扩大认证边界 | Web 扩展过期后仍需重新打开 |

## 5. 实施阶段

### 阶段 1：会话续期

- 修改范围：`apps/desktop-app/src/services/local-runtime.ts`、`main.ts`、preload/IPC 契约与定向测试。
- 步骤：增加单飞续签、续期计时器、停止清理、睡眠恢复续签和受信 IPC。
- 阶段验收：伪计时器验证重复续签、并发合并和停止后无续签。
- 回退点：删除新增续期入口，恢复启动时单次安装。

### 阶段 2：渲染器恢复与真实验证

- 修改范围：`apps/agent-console/src/features/tasks/api.ts` 及测试、打包产物。
- 步骤：本地 profile 的 401 调用 Desktop 续期并重试；盲迁移模型配置；重建并真实发送消息。
- 阶段验收：第一次 401、续签、第二次成功；真实 ModelCall 成功。
- 回退点：删除本地 401 分支，不影响企业 JWT refresh。

## 6. 契约、迁移与发布

- 兼容策略：新增可选 `desktopApi.localRuntime.renewSession`，旧 Web renderer 不调用。
- 数据迁移/回填：无数据库迁移；模型密钥只写入 safeStorage 密文。
- 发布顺序：测试源代码，再构建 renderer/runtime，最后打包并同 profile 重启。
- 回滚/恢复：保留上一版 app bundle；模型安全存储与 SQLite profile 不变。

## 7. 测试与验证矩阵

| 层级 | 场景 | 命令/入口 | 通过条件 |
|---|---|---|---|
| 单元 | timer、单飞、停止、IPC | Desktop Vitest 定向测试 | 无重复续签或停机后请求 |
| 单元 | 本地 401 自动续签 | Console API 测试 | 续签一次、原请求成功重试 |
| 集成/契约 | Web bootstrap | backend local-runtime tests | 单次消费与 Cookie 安全属性不变 |
| E2E/冒烟 | 长时等价与真实模型 | 短续期间隔 + 打包 CDP | 过初始 JWT 窗口等价场景仍成功 |

## 8. 风险与缓解

| 风险 | 概率/影响 | 早期信号 | 缓解/恢复 |
|---|---|---|---|
| runtime 重启与旧续签竞态 | 中/中 | 旧端口响应覆盖新 Cookie | generation 校验并在重启/停止清 timer |
| 多请求同时 401 | 中/中 | 重复 bootstrap 请求 | 主进程单飞 Promise |
| 系统睡眠跳过 timer | 高/中 | 唤醒后首请求 401 | `powerMonitor.resume` + 401 重试 |
| 凭据泄露 | 低/高 | 日志/命令出现 Key | 源内解析、IPC 盲传、仅报告元数据 |

## 9. 文档同步

- [x] `task-progress.yaml`
- [x] 当前 handoff 与 wiki log
- [x] 计划状态改为 completed

## 10. 完成定义

- [x] 所有阶段验收通过。
- [x] 适用测试、构建、重启和真实冒烟通过。
- [x] 认证边界与模型密钥不回显证据已记录。
- [x] 应用停留在默认工作区供用户检查。

## 11. 完成证据

- Desktop 全量测试：`38 files / 324 tests passed`；Console 401 续签定向测试：`31 passed`；backend local-runtime：`40 passed`。
- `npm run build:main`、`npm run build:renderer`、`npm run build:runtime` 与独立 macOS 目录包 `release-session-renewal` 均通过。
- 同一 profile 重启后，模型配置保持 `configured` / `persistent`，Provider 为 `chybenzun-openai-compatible`，Base URL 为 `https://chybenzun.top/v1`，模型为 `deepseek-v4-flash`。
- 将 `harness_local_session` 覆盖为无效值后，同一 `/api/agents/local-agent/connections` 请求先返回 401，IPC 自动续签重试返回 200；真实 Run `d255c87b-e96e-4772-974c-dc1eaf911b5d` 完成，ModelCall 为 `SUCCESS`，可见回复为 `SESSION_RENEWAL_OK_20260811`。
- API Key、Cookie 和 bootstrap token 均未写入 renderer 存储、URL、响应证据或日志输出。
