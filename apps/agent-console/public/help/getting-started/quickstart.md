# 快速开始

AI Harness 平台用 Harness 能力层把基础模型变成可审计、可评估、可运维的智能体。控制台是日常操作入口，FastAPI 服务是控制平面。首次验证时先用 Docker Compose 启动私有部署，打开控制台，完成初始化检查，然后从工作区运行一个智能体任务。

第一条有效交付证据不只是聊天回复，而是一条完整运行：包含计划、事件流、工具证据、沙箱边界、Trace 链接、Eval 可保存用例和可观测性记录。企业验收时应从运行详情检查这些证据，而不是只看模型输出文本。

```bash
docker compose --env-file deploy/docker-compose/.env.example -f deploy/docker-compose/docker-compose.yml up -d --build
```

启动后先检查 `/api/health/readiness`，确认数据库、Redis、模型供应商和后台任务依赖都处于可用状态。再进入控制台，按左侧导航检查智能体、工具、知识库、Eval、子智能体、可观测性和管理页面是否能正常打开。

上线前建议保留一条可重复执行的冒烟链路：创建或选择智能体，提交一个明确任务，确认运行完成，保存 Eval 用例，查看成本和 Trace，再用同一用例做回归。这样后续改动可以用相同证据判断是否破坏了核心链路。
