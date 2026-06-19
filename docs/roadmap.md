# Roadmap: Production Readiness

Status: `master roadmap`
Branch: continue on `p7-release-demo-hardening`
Predecessor: 功能阶段已完成（P0-P8 + Subagent v1-v3 + Tool Adapters v1-v2 + Observability v1）。本 roadmap 不加新功能，**专注让现有功能成为可落地的完整产品**。

## 1. 现状评估

代码侧已经齐：497 backend test、222 frontend test、27 个真 tool adapter、specialist marketplace、cost dashboard、trace UI。但从"功能完成"到"客户能拿走部署"，缺这 8 块：

| 维度 | 现状 | 落地差距 |
|---|---|---|
| **部署** | Docker Compose 能跑，但裸 HTTP、无反代、无 backup | 没法直接给客户用 |
| **首次体验** | 进来直接是 agent 列表，无引导 | 新用户不知道做什么 |
| **多用户** | dev_bearer token + org_id 隔离逻辑，但无真实登陆 / RBAC | 团队协作不可用 |
| **文档** | 12 份 dev docs，缺 user-facing help | 用户得读代码 |
| **前端 UX** | 功能齐，但 raw error / 无 retry / 无 skeleton / 无 error boundary | 体验粗糙 |
| **数据生命周期** | otel_spans/events/model_calls 无限增长 | 几个月后 DB 爆 |
| **CI/CD** | 无 GitHub Actions | 改动靠手工 push |
| **性能** | 单文件无 lazy load / 列表无 virtual scroll / 无 query cache | 数据多了就卡 |

## 2. 8 个 plan 优先级 + 依赖

按"对客户落地的边际价值 × 实施复杂度"排：

```
Phase A: 立刻能给客户演示
  P1. Production Deployment Hardening    [HIGH] [中工程]  独立
  P2. Onboarding & First-Run Experience  [HIGH] [中工程]  独立
  P5. Frontend Polish & UX               [MED]  [小工程]  独立

Phase B: 真正能给客户部署
  P3. AuthN/AuthZ + RBAC                 [HIGH] [大工程]  blocks P4 audit
  P6. Data Lifecycle & Retention         [MED]  [中工程]  blocks 长期运维
  P7. CI/CD + Release Engineering        [MED]  [中工程]  blocks 多人协作

Phase C: 长期可运维
  P4. Documentation & Help Center        [MED]  [小工程]  最后做（功能定型后）
  P8. Performance & Scale                [LOW]  [大工程]  按真实瓶颈做
```

**依赖关系**：
- P1 → 必须最先（部署都不通其他无意义）
- P2 → 与 P1 并行做（新用户从 Phase A 就能用）
- P3 → 多人/企业场景必须
- P6 → P3 之后（数据归属清楚才能清）
- P7 → P3 之后（CI 触发需要 secrets / 多人 review）
- P8 → P1+P3 之后（瓶颈出现再做）

## 3. 8 个 plan 概览

| ID | 名 | 文件 | 关键交付 | 估行 |
|---|---|---|---|---|
| P1 | Production Deployment Hardening | `prd-production-deployment-hardening-v1.md` | Compose 生产化 / Caddy 反代 + HTTPS / health probe / graceful shutdown / Helm chart / 外部 alert webhook / backup 脚本 | ~2500 |
| P2 | Onboarding & First-Run | `prd-onboarding-first-run-v1.md` | Dashboard 首屏 / 4 步配置向导 / Demo data 一键加载 / 全局 empty state / Quick Action | ~1800 |
| P3 | AuthN/AuthZ + RBAC | `prd-authn-authz-rbac-v1.md` | OAuth/邮件密码登陆 / RBAC (owner/admin/member/viewer) / API key 管理 / 用户管理 UI / Audit log UI / Workspace 切换 | ~3500 |
| P4 | Documentation & Help Center | `prd-documentation-help-center-v1.md` | README 重写 / 内置 /help 路由 / 重要按钮 tooltip / OpenAPI 整理 / troubleshooting guide | ~1200 |
| P5 | Frontend Polish & UX | `prd-frontend-polish-ux-v1.md` | ErrorBoundary / SSE 重连 / 大列表虚拟滚动 / Skeleton loading / 用户友好错误 / 前端 error tracking | ~2000 |
| P6 | Data Lifecycle & Retention | `prd-data-lifecycle-retention-v1.md` | Retention policy / Archive job / GDPR 数据删除 / Export 全量数据 / 防误删确认 | ~1500 |
| P7 | CI/CD + Release Engineering | `prd-cicd-release-engineering-v1.md` | GitHub Actions（lint/test/build/migration preflight/docker publish）/ semver release / canary deploy / smoke in CI | ~1500 |
| P8 | Performance & Scale | `prd-performance-scale-v1.md` | Query result cache / lazy route / virtual scroll / CDN / load test baseline / N+1 audit | ~2000 |

## 4. 建议派发节奏

**第 1 周**（并行）:
- P1 给 backend agent（部署 + Compose）
- P2 给 frontend agent（onboarding）
- P5 给 frontend agent（同时启动，与 P2 不冲突）

**第 2 周**（依赖前述）:
- P3 给 full-stack agent（最大工程，需 backend + frontend）
- P7 给 devops agent（CI/CD 独立）

**第 3 周**:
- P6 给 backend agent（retention）
- P4 给 doc agent

**第 4 周**:
- P8 按 P1-P7 暴露的瓶颈优化

**总工作量**：~16000 行净改动，按现在的 agent 节奏 3-4 周可全 ship。

## 5. 完成后的产品形态

Ship 完 8 个 plan 后，产品对外宣传应该是：

> **AI Harness Platform — 把 Model 变成可配置、可审计、可评估的企业 Agent**
>
> - 一行 docker-compose 部署到任意 Linux 主机（含 HTTPS / 自动备份 / 健康检查）
> - 4 步引导：选 LLM → 配模型 → 创 Agent → 跑 Demo，10 分钟完成
> - 多用户协作：OAuth 登陆 + RBAC + Audit log + Workspace 切换
> - 内置 Cost / Trace / Alert dashboard，外部 Slack/邮件告警
> - 27 个真实 tool adapter（GitHub/Slack/Notion/Linear/MCP）+ 9 类 Eval 契约 + Specialist marketplace
> - 内置 help center + tooltip + troubleshooting + OpenAPI 文档
> - GDPR-ready 数据删除 / Retention policy / 全量导出
> - GitHub Actions CI/CD + Canary deploy

## 6. 不在范围内（明确不做，留 v2+）

- **PaaS / 多区域**：客户自己买服务器，单实例 deployment
- **Mobile app**：仅 web console
- **Marketplace 公网商店**：仅内置 system + org-private specialist
- **真实 OAuth provider 自建**（Auth0/Keycloak/...）：v1 用 GitHub/Google
- **多语言支持完整翻译**：v1 中英两套
- **付费 / 计费系统**：开源版 + 自部署，无 SaaS billing

## 7. 给执行者的全局约束

1. **不加新业务功能** — 全部聚焦"让现有功能落地"
2. **不破坏现有 API** — 8 个 plan 全是 additive
3. **不动 P5-P8 / Subagent / Adapter / Observability 核心逻辑**
4. **每个 plan 独立可 ship** — 不要互相依赖（除明确标注的 blocks 关系）
5. **每个 plan 都用一致的 PRD 模板**（Why / What / 文件清单 / 测试 / DoD / 不做 / 风险 / 实施顺序）
6. **每个 plan 完工后必须**：wiki 4 处更新 + session 文件 + roadmap 行 + task-progress.yaml 段位

## 8. 下一步

8 个 plan 文件都已写到 `.omx/plans/prd-*.md`，按本 roadmap 推荐顺序派发即可。每个 plan 独立、可拆原子提交、有明确 DoD。
