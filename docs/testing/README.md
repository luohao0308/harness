# 测试与验证指南

_状态：active | 更新：2026-08-10_

## 1. 安全边界

- 在本地、CI 或独立测试环境运行，不连接生产数据和正式第三方账号。
- 测试配置使用 fake/mock、临时目录、容器或专用测试实例，不复制生产凭据。
- 诊断脚本、破坏性测试和外部集成测试必须与默认测试套件区分。

## 2. 命令入口

当前规格与用例入口： [eval-harness-spec.md](eval-harness-spec.md)、[benchmark-spec.md](benchmark-spec.md)、[evals/](evals/) 和 [qa/test-strategy.md](qa/test-strategy.md)。

| 检查 | 命令 | 工作目录 | 依赖 | CI 是否执行 |
|---|---|---|---|---|
| 收集/列出测试 | `.venv/bin/pytest --collect-only`；`npm test -- --list`（Vitest） | API/Console | 无生产依赖 | 否 |
| 定向单元测试 | `.venv/bin/python -m pytest tests/test_knowledge_rag.py`；`npm test -- src/features/...` | API/Console | 对应本地依赖 | 是 |
| 集成/契约测试 | `.venv/bin/pytest tests/integration tests/test_*api*.py`；OpenAPI generation | API/DB | PostgreSQL/Redis 或测试 fixture | 是 |
| E2E/冒烟 | `npm run e2e:smoke:release`；`python3 scripts/smoke-test-agent-run.py` | Console/root | browser + API/Compose | 按 release workflow |
| 覆盖率 | `npm run test:coverage`；后端按 CI/pytest 配置 | Console/API | 只作为对应 workflow 的门禁 | 按 workflow |
| lint/format | `ruff check app tests`；`npm run lint -- --pretty false` | API/Console | 无真实凭据 | 是 |
| 类型/静态检查 | Console `npm run lint`；Desktop `npm run type-check`；`node --check` | 客户端/脚本 | Node 20+ | 是 |
| 构建/编译 | Console `npm run build`；Desktop `npm run build:main`；Website `npm run build` | 各应用 | lockfile/平台依赖 | 是 |

## 3. 变更到测试的映射

| 改动范围 | 最低测试 | 升级为全量验证的条件 |
|---|---|---|
| 局部纯函数/组件 | 对应单元测试 | 公共接口或共享依赖变化 |
| 权限、安全、错误处理 | 定向安全回归 | 全局中间件/基础设施变化 |
| API/事件/Schema | 契约 + 消费方回归 | 破坏兼容或多消费者 |
| 数据模型/迁移 | 迁移演练 + 数据断言 | 生产数据回填/删除 |
| 配置/依赖/启动逻辑 | 静态检查 + 重启冒烟 | 发布或基础设施变化 |

## 4. 验证顺序

1. 定义要证明的声明和成功条件。
2. 先运行能快速区分正确/错误的定向检查。
3. 根据影响扩大到集成、全量、构建或 E2E。
4. 读取输出，不只记录退出码。
5. 失败则修正并重跑；无法运行则记录原因、影响和替代证据。

## 5. 提交前最小门禁

- [ ] 与改动直接相关的测试通过。
- [ ] lint、格式、类型或静态检查按项目要求通过。
- [ ] `git diff --check` 通过。
- [ ] 运行时变更已重启任务服务并冒烟。
- [ ] 契约、迁移、生成物和文档同步检查完成。

## 6. 当前发布门禁参考

完整门禁以 [开发贡献指南](../development/CONTRIBUTING.md) 和 `.github/workflows/` 为准；常用最低集为 API pytest/Ruff、Console lint/build、Desktop 受影响测试、`python3 scripts/validate-docs.py` 与 `git diff --check`。
