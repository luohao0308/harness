# Git 历史重排与单维护者 OPC 交付

Category: `session-log`

Tags: `git`, `history`, `delivery`, `opc`, `github`, `ci`

## 目标

在不改动既有 Git 作者时间和提交时间的前提下，把已发布功能分支整理为可审阅的交付历史；同时为单人维护项目建立接近成熟工程团队、但不过度膨胀的日常交付流程。

## 结果

- 原始分支 `codex/desktop-team-ai-provider` 保持在 `6796bfed9555ae5f8f09b5c0b26b8ab94330369c`。
- 只读回退分支 `archive/2026-08-16-codex-desktop-team-ai-provider-before-rewrite` 指向同一原始提交。
- 新交付分支为 `feat/platform-desktop-delivery`。
- 严格重排后的历史终点为 `b5d04a5cd919e99b5c4432ba837320da71bd9cd3`；新增工作流提交为 `0f7ee3acc7f5dbdaa6f81ec3cd74c2211be9e772`。
- GitHub PR [#34](https://github.com/luohao0308/harness/pull/34) 已从新交付分支创建到 `main`，等待 CI 和合并决策。
- `main` 仍为 `fa5425eb20bb8a011d134877009d921c06f4bf1e`；没有强推、删除旧分支、重写 `main` 或合并 PR。

## 严格保时边界

本次重排逐提交保留：

- 完全相同的文件树 SHA；
- 完全相同的作者身份与 author date；
- 完全相同的提交者身份与 committer date；
- 映射后的父提交关系和 9 个 merge 的拓扑；
- 原提交正文。

仅提交标题被整理为 scoped Conventional Commits。共保留 107 个历史提交、9 个 merge、73 个 first-parent 提交。原始历史终点和重排历史终点的树差异为零。

GitHub 的分支推送时间、Actions 时间和 PR 创建时间属于平台事件，Git 对象不能控制或回填这些时间；这里的“不改变提交时间”指 Git 对象内的 author date 与 committer date 精确不变。

## 单人 OPC 日常流程

日常交付保持四步：

1. 从稳定 `main` 创建短生命周期 `feat/*`、`fix/*` 或 `chore/*` 分支。
2. 使用 `type(scope): summary` 提交；标题不超过 88 个字符。
3. 本地 hook 只做暂存区 whitespace 和提交信息检查，重验证交给 CI。
4. PR 写清 Intent、Changes、Validation、Risk/Rollback、Evidence；CI 通过后 squash merge，分支随后删除。

仓库没有引入 Husky、commitlint、semantic-release 或额外 `develop` 分支。提交策略由 `.githooks/`、`scripts/validate-commit-message.py` 和 `.github/workflows/pr-check.yml` 共同锁定；`scripts/install-git-hooks.sh` 完成单次安装。

## 验证证据

- 本地严格重排 manifest 覆盖 107/107 个历史提交，逐项核对 tree、author date、committer date 和 parents。
- `git fsck --full --no-dangling` 通过。
- 提交策略测试 5/5 通过，Python 编译、Shell 语法和 GitHub Actions YAML 解析通过。
- 所有重排后的非 merge 标题和 PR 标题均通过同一校验器。
- 文档结构校验、Markdown 本地链接校验和新增提交 whitespace 检查通过。
- 远端四个关键 ref 已核对：`main`、原始分支未变化；归档分支和新交付分支已发布。

## 后续边界

PR 合并和以 `--force-with-lease` 替换旧分支都属于独立的破坏性/生产 Git 决策。本次不自动执行；默认推荐在 PR 通过后合并新分支，并继续保留归档分支一段观察期，而不是覆盖旧分支。
