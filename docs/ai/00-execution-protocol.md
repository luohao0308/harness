# 00 AI 执行协议

本文件定义 AI Agent 执行项目的固定流程。任何 AI 接手本项目时，必须先读取本文件，再读取 [任务进度](./01-task-progress.md)。

## 角色定义

AI 的角色是工程执行 Agent。AI 不做技术选型讨论，不改变架构决策，不跳过阶段，不把未来阶段内容提前实现。

## 单阶段执行循环

AI 每次执行任务时必须按以下顺序运行：

```text
1. 读取 docs/ai/README.md
2. 读取 docs/ai/00-master-prompt.md
3. 读取 docs/ai/00-execution-protocol.md
4. 读取 docs/ai/01-task-progress.md
5. 读取 docs/ai/task-progress.yaml
6. 使用 task-progress.yaml 的 current_stage 定位阶段文档
7. 读取该阶段文档
8. 复制该阶段文档中的 AI 执行提示词作为本阶段任务
9. 读取该阶段 Required Context 列出的参考文档
10. 执行阶段任务
11. 执行阶段 Verification Commands
12. 执行 git status --short
13. 创建阶段 commit
14. 推送阶段分支到 origin
15. 创建 Pull Request
16. 更新 docs/ai/task-progress.yaml
17. 更新 docs/human/10-task-progress.md
18. 输出阶段完成摘要
19. 停止，等待用户合并 PR；连续执行模式下也必须等待当前 PR 合并后再进入下一阶段
```

## 任务进度更新规则

完成阶段后，AI 必须在 [机器可读任务进度](./task-progress.yaml) 中更新：

```text
status
started_at
completed_at
changed_files
verification_commands
verification_result
branch
commit_sha
pr_url
notes
next_stage
```

`verification_result` 必须写入 `passed`、`failed`、`blocked` 三者之一。

## 阶段状态枚举

```text
pending
in_progress
ready_for_review
completed
blocked
failed
```

## 分支与 PR 规则

每个阶段必须独立分支开发：

```text
stage/<stage-id>
```

阶段开始命令：

```bash
git fetch origin
git checkout develop
git pull --ff-only origin develop
git checkout -b stage/<stage-id>
```

验证通过后必须提交、推送、创建 PR：

```bash
git status --short
git add <changed-files>
git commit -m "feat(<stage-id>): complete stage"
git push -u origin stage/<stage-id>
gh pr create --base develop --head stage/<stage-id> --title "feat(<stage-id>): complete stage" --body-file .github/pull_request_template.md
```

没有 GitHub CLI 时，AI 必须推送分支并在输出中提供 GitHub Web 创建 PR 的 URL。

阶段创建 PR 后，阶段状态写为 `ready_for_review`。用户合并 PR 后，阶段状态写为 `completed`，再进入下一阶段。历史补录阶段使用 `legacy_no_pr` 填写 branch、commit_sha、pr_url、merged_at；新阶段禁止使用 `legacy_no_pr`。

## 禁止事项

- 禁止跳过任务进度更新。
- 禁止在 main 分支或 develop 分支直接开发阶段任务。
- 禁止未创建 PR 就把阶段标记为 completed。
- 禁止在 PR 未合并时进入下一阶段。
- 禁止在未读取阶段文档时执行阶段任务。
- 禁止把多个阶段混成一次大改。
- 禁止更换固定技术栈。
- 禁止把 Gemini/H5 代码直接作为生产代码。
- 禁止在宿主机直接执行 Agent shell 工具。
- 禁止直接调用模型供应商 SDK，业务代码必须调用 Model Gateway。
- 禁止删除 Event Store 事件。
- 禁止在文档中恢复松动表达。

## 阻塞处理

遇到缺少账号、远程仓库、Figma 链接、密钥、Docker 权限、端口占用、依赖安装失败时，AI 必须：

```text
1. 将当前阶段 status 改为 blocked
2. 在 notes 写明阻塞原因
3. 在 notes 写明需要用户提供的具体信息
4. 不进入下一阶段
```

## 阶段执行输出格式

AI 完成每个阶段后，必须输出：

```text
阶段：
状态：
完成内容：
变更文件：
验证命令：
验证结果：
分支：
Commit：
PR：
下一阶段：
```

## 连续执行模式

用户明确要求“连续执行”时，AI 在完成当前阶段并更新任务进度后，继续读取下一阶段文档。用户未明确要求连续执行时，AI 在每个阶段结束后停止。
