# Team 概览与 Agent 专注融合方案

## 结论

参考截图带来的关键变化不是换皮，而是信息组织分成两种工作节奏：

- 参考图 1 适合“不细看”：主对话旁边用并行成员任务行和系统看板展示整体推进，用户无需逐个打开 Agent。
- 参考图 2 适合“需要判断”：单个对话与任务依赖结构并排，用户可以从消息证据追到任务关系。
- 当前 Harness Team 基线已经完成 Apple/Codex 风格 P0/P1/P2 收敛，视觉问题已从卡片堆叠降到低噪声连续平面；下一步应补信息层级，而不是再次堆叠面板。

最终融合模型：

```text
协作 = 团队概览（默认快速扫描）
  ├─ 目标与完成度
  ├─ 成员进度行（点击进入专注）
  └─ 右侧系统看板（阻塞 / 失败 / 最近活动 / 人工待处理）

专注 = 单 Agent 完整对话（深入阅读与操作）
  ├─ 稳定 760px 消息阅读列 + composer
  └─ 按需打开任务详情或依赖图

任务图 = 结构审查工具（默认不抢首屏）
多列 = 专家并行模式（现有能力保留）
```

## 保留项

- Team API、SSE、mailbox、wake、任务、目标、事件和桌面 IPC 语义全部保留。
- `协作 / 任务图 / 多列` 仍是桌面视图能力；浏览器默认多列不变。
- Team tabs、roster、inspector、AgentColumn、任务图和每列 composer 均保留，重新划分职责。
- 单 Agent 深度对话保留消息流、流式状态、停止/继续、复制、编辑、分支、上下文压缩、运行详情、文件和审批入口。
- 既有 `760px` 阅读列、低对比中性色、中文优先、无持续 pulse、窄屏无溢出作为视觉和交互基线。

## 新增职责

- `TeamOverviewSurface`：聚合 Team、目标、任务和事件的可比较摘要；不展示完整聊天。
- `TeamSystemBoard`：只显示需要判断的系统状态，不复制活动消息流。
- `TeamAgentFocusSurface`：复用当前 Agent 对话实现，按 Agent 保留草稿、滚动、未读和流式状态。

## 实施边界

实施计划见 [`docs/plans/desktop-team-overview-focus-2026-08-13.md`](../docs/plans/desktop-team-overview-focus-2026-08-13.md)，分三阶段：

1. 先建立概览入口、成员进度行和专注入口。
2. 再加入系统看板和专注内按需任务上下文。
3. 最后处理 1440 桌面、1024-1199 窄桌面和 390 移动端布局，并做 Visual Ralph 复核。

当前实现已完成三阶段的前端融合：Electron 桌面 `协作` 默认进入概览，成员行进入单 Agent 专注；专注顶部可返回概览，宽屏可在检查器与任务图之间按需切换，任务图/多列独立视图和浏览器默认多列保留。实现只组合现有 Team、目标、任务、消息和 wake 数据，没有新增后端聚合接口或改变 Team API、SSE、mailbox、IPC 语义。

阶段 1-3 的验证证据：Team Vitest `27/27`；Playwright Chromium smoke `3/3`（1440px 协作/任务图/多列、窄桌面专注、团队创建与多列、390px 单列无溢出）；Agent Console TypeScript/lint/build 通过。后续只需在真实 Electron 窗口做一次视觉复核，不阻塞当前功能交付。

## 证据

- 当前 Team UI 基线截图：`/var/folders/j3/1pxq4hf53bn1df3r6mvmw3zw0000gp/T/codex-clipboard-bf279e83-50d2-439f-8f47-b80bd544dc81.png`
- 并行 Agent 概览参考：`/var/folders/j3/1pxq4hf53bn1df3r6mvmw3zw0000gp/T/codex-clipboard-4c6ef58c-f5ad-480f-85aa-efb46ad95bff.jpg`
- 对话与任务图参考：`/var/folders/j3/1pxq4hf53bn1df3r6mvmw3zw0000gp/T/codex-clipboard-91946013-7478-418b-9512-f021287e5670.png`
- 既有 P0/P1/P2 验证：Team Vitest `27/27`、Playwright smoke `3/3`、lint/build/docs/link/diff 通过、Visual Ralph `91/100 PASS`。
