# GitHub 与 Git 交付工作流

本文件是 Harness 分支、提交、PR、Review 和 Release 的详细权威入口。根目录 `CONTRIBUTING.md` 保留最短的人读规范；两处必须保持一致。

## 1. 设计目标

- `main` 始终可部署、可回滚、可打 Release tag。
- 日常工作使用短生命周期分支，不维护单人项目不需要的长期集成层。
- 每个交付通过 commit title、PR、CI、Release tag 和验证证据形成闭环。
- 不伪造第二位 Reviewer，不用重量级工具替代现有 GitHub Actions。

## 2. 分支模型

| 分支 | 用途 | 合并目标 | 生命周期 |
|---|---|---|---|
| `main` | 稳定、可发布主线 | - | 长期 |
| `feat/<scope>-<short-name>` | 产品或功能变化 | `main` | 一个 PR |
| `fix/<scope>-<short-name>` | 缺陷修复 | `main` | 一个 PR |
| `docs/<short-name>` | 文档变化 | `main` | 一个 PR |
| `chore/<short-name>` | CI、工具或工程维护 | `main` | 一个 PR |
| `release/<version>` | 多平台 Release candidate | `main` | 发布窗口 |
| `hotfix/<short-name>` | 生产紧急修复 | `main` | 一个 PR |

`develop` 不再是日常必经分支。历史 `develop` ref 保留到连续两个 Release 完成后再决定是否归档；不得在普通功能交付中继续向它堆积新提交。

Agent 临时 worktree 可以使用 `codex/` 前缀，但面向交付的 PR branch 使用上表中的产品范围命名。

## 3. 开始任务

先确认仓库、远端和工作树：

```bash
git rev-parse --show-toplevel
git worktree list --porcelain
git status --short --branch
git fetch origin --prune
```

从当前 `origin/main` 创建独立 worktree：

```bash
git worktree add ../harness-feat-team \
  -b feat/team-overview-focus \
  origin/main
cd ../harness-feat-team
scripts/install-git-hooks.sh
```

不复用归属不明的 worktree，不覆盖用户已有改动，不在产品仓库内部嵌套新 worktree。

### 大型计划拆分门

大型计划在创建开发 worktree、修改产品代码或创建交付 PR 前，先按 [AI 执行协议](ai/00-execution-protocol.md) 自动拆成 `2-6` 个切片，并向用户展示目标、范围、依赖、验收和回退点。状态保持 `awaiting_user_confirmation`，直到用户批准或调整拆分。

确认后将切片写入 `docs/plans/`。默认整个计划使用一个短分支和一个 PR，每个切片形成可验证的提交或检查点；只有切片可以独立发布、需要不同回滚窗口或必须隔离高风险时才拆成多个 PR。每次只推进一个切片，完成验证并记录证据后自动进入下一个，不逐片重复等待用户。

如果新事实实质改变已确认的范围、顺序、接口、迁移或风险，暂停后续提交，展示修订前后差异并重新确认；切片内部的普通实现调整不触发新的确认轮次。

## 4. 提交规范

标题格式：

```text
<type>(<scope>): <imperative summary>
```

允许的 type：

```text
feat fix refactor docs test chore ci build perf revert
```

规则：

- scope 使用小写 kebab-case，例如 `team`、`local-agent`、`desktop-team`。
- 完整标题不超过 88 个字符，不以句号结束。
- 一个提交只包含一个可解释、可验证的行为切片。
- 非 trivial body 只写 Why、Impact、Validation；未运行的检查不能写成已通过。
- 本地允许 `fixup!` / `squash!`，PR 前必须折叠。

示例：

```text
feat(team): add overview and focused conversation

Why: give desktop Team users a scan-first entry without losing full dialogue.
Impact: desktop Collaboration defaults to overview; browser columns stay unchanged.
Validation: Team Vitest; Playwright Team smoke; Console build.
```

精确暂存：

```bash
git status --short
git diff -- <owned-files>
git add -- <owned-files>
git diff --cached --check
git diff --cached
git commit
```

禁止使用 `git add .` 或 `git add -A` 暂存范围不明的文件。

## 5. 三层验证

### 每个 commit

- `.githooks/pre-commit`：`git diff --cached --check`。
- `.githooks/commit-msg`：调用 `scripts/validate-commit-message.py`。
- 运行变更直接相关的最小测试。

### 每个 PR

`.github/workflows/pr-check.yml` 校验：

- PR title 与所有非 merge commit subject；
- backend Ruff 与 pytest；
- frontend lint、test、build 与 bundle budget；
- migration ID 与 upgrade preflight；
- 文档和 Markdown 链接；
- whitespace。

跨模块、迁移、安全和 Release 变化应在 push 前本地运行完整适用门禁。纯文档或局部 UI 调整无需让每个 commit 重跑全仓测试。

### 每个 Release

Release tag 必须可达 `main`。`.github/workflows/release.yml` 负责镜像、Helm、Desktop、启动预算和 GitHub Release；实际签名、公证和生产发布仍需要相应凭据与授权。

## 6. Pull Request

PR 目标统一为 `main`。PR title 与最终 squash commit 使用同一个 Conventional Commit 标题。

```bash
git push -u origin HEAD
gh pr create \
  --base main \
  --title "feat(team): add overview and focused conversation" \
  --body-file .github/pull_request_template.md
```

PR 描述只保留五项：Intent、Changes、Validation、Risk/Rollback、Evidence。UI 改动附截图；API、事件、Schema、迁移、Desktop IPC 或部署改动同步对应契约与 Runbook。

## 7. Review 与合并

单人 OPC 的 required gates：

- 所有 required CI checks 通过；
- PR 自审清单完成；
- 没有未解释的 migration、secret、runtime 或 rollback 风险；
- 当前任务文档和证据已按 `AGENTS.md` 回写。

不要创建虚假的第二人 Review。出现长期协作者后再启用真实 approval requirement。

默认使用 squash merge，让 `main` 每个 PR 只留下一个交付 commit；合并后删除短分支。Merge commit 仅用于必须保留拓扑的历史集成或 Release 场景，并在 PR 中写明原因。

禁止直接推送 `main`。禁止 `git push --force`。远端历史改写只允许在已建立 archive ref、通过 old/new 验证并获得明确授权后使用 `--force-with-lease`，且不得用于 `main`。

## 8. Release 与 Hotfix

准备版本：

```bash
scripts/release.sh patch
```

验证并把版本变更通过 PR 合入 `main` 后：

```bash
git checkout main
git pull --ff-only origin main
git tag -a v0.1.1 -m "Release v0.1.1"
git push origin v0.1.1
```

Hotfix 从 `origin/main` 创建 `hotfix/*`，运行定向回归和完整适用门禁，通过 PR squash 回 `main`，再按需要补 patch tag。无需再手工同步到 `develop`。

完整发布、Canary、Desktop 签名/更新和回滚步骤见 `docs/project-memory/runbooks/release.md`。

## 9. 本地策略安装与测试

```bash
scripts/install-git-hooks.sh
python3 scripts/test-commit-message-policy.py
```

hooks 只做标题和 staged whitespace 检查，不在每次 commit 跑全仓测试。CI 与 hook 调用同一个 stdlib validator，避免本地与远端规则漂移。

## 10. 文档与安全边界

- 业务代码、API、事件、Schema、迁移、部署或 UI 行为变化时，按 `docs/development/README.md` 的影响矩阵同步权威文档。
- 当前任务状态写 `docs/TASKS.md`，机器进度写 `docs/development/ai/task-progress.yaml`，完整证据写相关 `omx_wiki/` session。
- 模型密钥、Token、Cookie、私钥、签名 URL 和真实部署凭据不得进入 commit、PR、CI output 或历史重整 manifest。
- Branch Protection 的最低建议是：禁止直接 push `main`、要求 PR、要求 commit-policy 和现有 CI checks、允许单人维护者在 checks 通过后 squash merge。
