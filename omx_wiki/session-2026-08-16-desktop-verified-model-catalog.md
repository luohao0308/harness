# Desktop 已验证模型目录收敛

Category: `session-log`

Tags: `desktop`, `model`, `discovery`, `provider`, `delivery`

## 目标

将 Desktop 当前使用的新 OpenAI 兼容服务落实为可交付的默认目录，避免旧平台目录继续展示当前密钥不可用的模型。

## 结果

- 默认 Base URL 更新为 `https://ai.112102.xyz/v1`。
- 默认模型更新为 `minimax-m3`。
- 平台目录收敛为 5 个已验证模型：
  - `deepseek-v4-flash`
  - `gpt-oss-120b`
  - `mimo-v2.5`
  - `minimax-m3`
  - `nvidia-gpt-oss`
- Desktop 本地运行时对该服务保留 5 模型 allowlist；自定义 URL 或未知手动模型仍只允许单项，保持 fail-closed。
- Agent Console 的平台目录同步收窄，前端仍会与后端实际 allowlist 求交集后再展示。
- API Key 没有写入仓库，继续使用已有 Electron `safeStorage` 配置。

## 验证

- 远端发现返回上述 5 个模型。
- 5 个模型分别进行了真实自然语言调用，均为 `HTTP 200`、Run `COMPLETED`、ModelCall 成功。
- Desktop 重启后恢复 `minimax-m3`、新 Base URL 和持久化安全密钥。
- 重启后随机中文消息返回非空自然回复，Run `COMPLETED`。
- 后端定向测试 `62 passed`，模型网关/Team Runtime `60 passed`，模型设置页 `13 passed`。

## 边界

当前仓库只提交模型目录、默认值和 allowlist 逻辑；真实 API Key 仍属于本机运行时状态，不进入 Git、日志或前端存储。
