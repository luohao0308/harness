# 01 任务进度

任务进度的唯一事实源是 [task-progress.yaml](./task-progress.yaml)。AI 和 CI 只读取、更新、校验 YAML 文件。

## 使用规则

- 当前阶段读取 `current_stage`。
- 当前状态读取 `current_status`。
- 下一阶段读取 `next_stage`。
- 每个阶段的执行记录写入 `stages[]` 中对应条目。
- 阶段完成后必须更新 `changed_files`、`verification_commands`、`verification_result`、`notes`。
- `verification_result` 固定为 `passed`、`failed`、`blocked` 三者之一。

## 阶段状态

```text
pending
in_progress
completed
blocked
failed
```

## 更新流程

```text
1. 读取 docs/ai/task-progress.yaml
2. 定位 current_stage
3. 执行阶段任务
4. 执行 Verification Commands
5. 更新当前阶段记录
6. 更新 current_stage、current_status、last_updated_at、last_updated_by、next_stage
7. 保存 task-progress.yaml
```

## YAML 结构

```yaml
current_stage: stage-01-git-github
current_status: pending
last_updated_at: null
last_updated_by: null
next_stage: stage-01-git-github
stages: []
```

