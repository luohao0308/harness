# Desktop 动态模型目录与重启持久化

Category: `implementation`

Tags: `desktop`, `model`, `discovery`, `allowlist`, `persistence`, `delivery`

## Outcome

Desktop 的模型目录改为“显式检测 -> 用户保存 -> 本地运行时重启恢复”的动态链路。目录不再由某个供应商 URL 的五个硬编码 ID 决定；后端 allowlist、桌面设置页和高级模型设置页都以当前保存的 provider rows 为权威。

## Implementation

- Electron preload/IPC 的配置输入新增可选 `models`，主进程对模型 ID 做字符集、长度、数量上限和去重校验；目录与 Base URL、默认模型一起原子写入既有 `0600` profile。
- `harnessd` bootstrap 新增 `model_ids`。旧 profile 或没有可信目录时回退到当前模型；同一 URL/模型重新保存而未重新检测时保留既有目录。
- FastAPI local-runtime 配置接受动态目录，显式目录必须包含当前模型；Base URL/模型变化且未携带目录时退化为 singleton allowlist。供应商 URL 特判和五模型常量已删除。
- Desktop 设置页把发现结果绑定到规范化 Base URL；地址变化立即清除旧结果，只有同地址目录且选中模型仍在其中时才随 Save 发送。
- 高级模型设置页从后端 provider rows 构建平台目录。静态目录只提供已知模型友好名称，后端返回的新 ID 使用原始 ID 展示，因此不可用旧模型不会继续出现。

## Evidence

- Backend: `1544 passed`; local-runtime targeted regression `47 passed`; Ruff passed。
- Agent Console: settings/API targeted regression `43 passed`; lint and production build passed with `2414` modules。
- Desktop: `38 files / 326 tests passed`; main build passed。
- Packaged artifact: `apps/desktop-app/release-dynamic-model-catalog/mac/Harness Desktop.app` built successfully。
- Live packaged smoke: provider discovery returned six models (`deepseek-v4-flash`, `glm-5.2`, `gpt-oss-120b`, `mimo-v2.5`, `minimax-m3`, `nvidia-gpt-oss`); Save returned the same six backend models; same-profile restart restored the six-model catalog and `minimax-m3` while changing the loopback port; a randomly selected Chinese prompt returned a non-empty natural response。
- No API key, response credential, or secret profile content was written to tracked files or command output.

## Delivery

- `7209df2 feat(desktop): persist discovered model catalog`
- `d912884 feat(runtime): use discovered models for local allowlist`
- `4f78de7 feat(settings): surface runtime model catalog`
- S4 follow-up commit records the identity-preserving save edge case, final regression evidence, and documentation write-back.

## Remaining Risk

The Console full-suite single-fork run had one order-sensitive `workspaceScope` failure; the isolated test rerun passed `2/2`. The model-directory tests and build are green. The dynamic list refreshes only on explicit user discovery, by design, so provider catalog changes remain user-triggered rather than startup-blocking.
