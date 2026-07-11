# RPA Phase 2 Electron Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不恢复 Go RPA 的前提下，为当前项目分阶段落地一个由 Python 托管的 Electron + TypeScript 无主界面桌面 RPA Runtime，并确保每一阶段都可独立验收。

**Architecture:** Python 负责 Runtime 生命周期、鉴权和业务映射；Electron Runtime 负责本机窗口、截图、校准、输入与视觉校验；前端继续仅调用 Python。实施按 2A～2F 严格分段推进，上一段未验收不得进入下一段。

**Tech Stack:** Python 3.11+, Quart, Electron, TypeScript, npm, Node 22 LTS, electron-builder, Vitest, mock input driver

---

## Scope Gate

本计划只描述未来实施步骤，不代表现在开始编码。执行前必须再次确认。

硬门禁：

1. 不修改非 RPA 相关工作树文件；
2. 不恢复任何 Go runtime；
3. 2C 实机 `paste_only` 未通过前，禁止进入 2D～2F；
4. 未经用户后续单独批准，不做真实发送实机测试。

---

## File Structure Preview

### 新增 Runtime 工程

- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\package.json`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\package-lock.json`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\electron.vite.config.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\electron-builder.yml`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\SOURCE_MANIFEST.md`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\THIRD_PARTY_NOTICES.md`

### Python 对接层（未来阶段按需修改）

- Modify later: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- Modify later: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py`
- Modify later: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Modify later: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\repository.py`
- Modify later: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`

### 前端对接层（未来阶段按需修改）

- Modify later: `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api\bot-database.ts`
- Modify later: `C:\Users\33031\Desktop\bot\web\src\app\infra\http\BackendClient.ts`
- Modify later: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseBotSessionMonitor.tsx`

---

## Phase 2A: Runtime 骨架、鉴权、health、Python 托管

**Objective:** 先建立最小可启动的 Electron Runtime，与 Python 完成安全握手与健康检查，但不做任何真实桌面动作。

**Files:**
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\index.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\bootstrap\handshake.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\api\local-http-server.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\api\auth.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\api\routes-health.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\domain\runtime-types.ts`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\runtime_process.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_client.py`

- [ ] 定义 Runtime 启动契约：token 通过环境变量或受控 stdin 传入，stdout 仅返回 `pid/port/protocolVersion/runtimeVersion`。
- [ ] 在 Runtime 内实现 `127.0.0.1:0` 随机端口监听与 `/healthz`。
- [ ] 在 Runtime 内实现 Bearer token 中间件，禁止空 token、禁止 token 落盘、禁止 token 进入日志。
- [ ] 在 Python `runtime_process.py` 中实现子进程启动、stdout 解析、内存态连接信息保存。
- [ ] 在 Python `client.py` 中实现 `/healthz`、`/v1/runtime/status` 最小调用。
- [ ] 为启动超时、协议版本不匹配、认证失败写单元测试。
- [ ] 运行验证：
  - `uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_runtime_process.py -q`
  - `uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_client.py -q`
  - `npm run typecheck`
  - `npm run lint`
- [ ] 2A 验收标准：
  - Python 能启动 Runtime；
  - Runtime 不写 `runtime-info.json`；
  - token 不出现在 stdout / 日志 / 文件中；
  - `/healthz` 与 `/v1/runtime/status` 可用。

---

## Phase 2B: 窗口发现、绑定、DPI、Overlay、RegionProfileV2

**Objective:** 落地窗口发现/绑定/重新发现、多显示器/DPI 与 Overlay 校准，建立 `RegionProfileV2`。

**Files:**
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\window\window-finder.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\window\window-activator.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\window\window-binder.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\window\window-validator.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\window\display-metrics.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\overlay\overlay-window.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\overlay\overlay-session.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\domain\region-profile.ts`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\repository.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_repository.py`

- [ ] 定义 `WindowDescriptor` 与增强版 `WindowBinding` 结构。
- [ ] 实现按 `executablePath + processName + appType` 的重新发现策略。
- [ ] 实现“多个候选即阻断”的发现规则，返回 `WINDOW_CANDIDATE_AMBIGUOUS`。
- [ ] 实现 Overlay 校准，限制单次 profile 的全部区域位于同一 display。
- [ ] 在 Runtime 端定义 `RegionProfileV2`，仅持久化 `normalizedToClient` 与 baseline。
- [ ] 在 Python repository 中增加 `schemaVersion=2` 校验，拒绝旧 Go profile。
- [ ] 编写多显示器/DPI 变换单元测试。
- [ ] 编写 Python profile schema gate 单元测试。
- [ ] 运行验证：
  - `uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_repository.py -q`
  - `npm test`
  - `npm run typecheck`
- [ ] 2B 验收标准：
  - 能人工完成一次 `RegionProfileV2` 校准；
  - 发现多个窗口候选时 fail-closed；
  - 旧 Go profile 被明确拒绝；
  - DPI 与 display 基线可记录并用于运行时校验。

---

## Phase 2C: safe typing zone、剪贴板、`paste_only`

**Objective:** 在不发送的前提下完成安全聚焦、剪贴板快照/恢复、`paste_only` 和结构化验证错误。

**Files:**
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\input\mouse-controller.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\input\click-safety.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\input\clipboard-controller.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\input\paste-controller.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\capture\capture-service.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\capture\region-screenshot.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\message-diff.ts`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\api\http\controller\groups\bot_database_mode.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py`
- Test: `C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py`

- [ ] 实现 `inputSafePoints` 计算与 editable-area 校验。
- [ ] 实现剪贴板支持矩阵：`text/html/rtf/image`。
- [ ] 在覆盖剪贴板前检测不支持格式，返回 `CLIPBOARD_FORMAT_UNSUPPORTED`。
- [ ] 实现 `paste_only`：聚焦、粘贴、输入区变化验证。
- [ ] 实现最多一次备选安全点重试，且重试前重新验证窗口/会话/安全点。
- [ ] 实现结构化错误：
  - `INPUT_FOCUS_FAILED`
  - `PASTE_NOT_OBSERVED`
  - `WINDOW_FOCUS_LOST`
  - `REGION_PROFILE_INVALID`
- [ ] 实现 `succeeded_with_warning` + `clipboardRestoreFailed=true` 返回路径。
- [ ] 在 Python `/paste-draft` 链路中接入 Runtime paste task。
- [ ] 使用 mock input driver 写单元测试与集成测试。
- [ ] 完成 2C 实机 `paste_only` 验收。
- [ ] 运行验证：
  - `uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_service.py -q`
  - `uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\test_api.py -q`
  - `npm test`
- [ ] 2C 验收标准：
  - `paste_only` 在实机可用；
  - 不会发送；
  - 剪贴板支持边界明确；
  - 恢复失败会以 warning 返回。

> **Hard Gate:** 2C 实机 `paste_only` 未通过前，禁止进入 2D～2F。

---

## Phase 2D: 截图、diff、红点、VLM

**Objective:** 在 `paste_only` 稳定后，补齐截图、diff、红点检测与 VLM 辅助视觉能力。

**Files:**
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\capture\window-screenshot.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\capture\dpi-transform.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\ai-client.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\red-dot-detector.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\layout-detector.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\bbox-parser.ts`
- Test: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\__tests__\*.test.ts`

- [ ] 实现统一截图返回模型。
- [ ] 实现 `pixelmatch` 风格 diff。
- [ ] 实现红点检测双路径：像素优先、VLM 兜底。
- [ ] 实现本地 provider hub 的 vision provider 装载。
- [ ] 为 VLM 结果解析与失败路径写单元测试。
- [ ] 运行验证：
  - `npm test`
  - `npm run typecheck`
  - `npm run lint`
- [ ] 2D 验收标准：
  - 截图、diff、红点、VLM 均可独立测试；
  - provider 仅支持本地 provider；
  - 日志不泄露截图与 key。

---

## Phase 2E: 会话搜索、历史搜索、引用回复

**Objective:** 增加会话级定位能力，但严格要求会话验证与歧义阻断。

**Files:**
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\vision\session-verifier.ts`
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\runtime\task-runner.ts`
- Modify: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\api\routes-actions.ts`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\client.py`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`

- [ ] 实现会话标题截图 + 期望会话名称 + 视觉匹配的会话验证器。
- [ ] 实现 conversation-search 任务。
- [ ] 搜索后点击结果必须再次会话验证。
- [ ] 候选不唯一时返回 `CONVERSATION_AMBIGUOUS`。
- [ ] 为 history-search / quote-reply 只先落接口与校验骨架。
- [ ] 使用 mock screenshot / mock vision provider 写集成测试。
- [ ] 运行验证：
  - `npm test`
  - `uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\ -q`
- [ ] 2E 验收标准：
  - 搜索后不经二次验证不得进入粘贴；
  - 候选不唯一必定阻断；
  - 会话验证可被 Python 业务链路消费。

---

## Phase 2F: `auto_send`、打包和分发

**Objective:** 在前几段通过后，完成受控 `auto_send`、打包、原生模块 rebuild 与 Windows 分发准备。

**Files:**
- Create: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\src\main\input\send-controller.ts`
- Modify: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\package.json`
- Modify: `C:\Users\33031\Desktop\bot\apps\desktop-rpa-runtime\electron-builder.yml`
- Modify: `C:\Users\33031\Desktop\bot\src\langbot\pkg\desktop_automation\service.py`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\entities\api\bot-database.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\infra\http\BackendClient.ts`
- Modify: `C:\Users\33031\Desktop\bot\web\src\app\home\bots\components\bot-session\components\DatabaseBotSessionMonitor.tsx`

- [ ] 实现 `enter | ctrl_enter | click_send_button` 三选一发送策略。
- [ ] 禁止失败后自动尝试其他策略。
- [ ] 把 `auto_send` 保持为编译完成但运行时默认禁用。
- [ ] 加入启用门槛校验：
  - 前端明确动作
  - Python 明确授权
  - Runtime 配置开启
  - 会话验证通过
  - 窗口绑定通过
  - 草稿 digest 匹配
- [ ] 发送链路仅使用 mock input driver 做单元/集成测试。
- [ ] 固化 npm 脚本：
  - `npm run typecheck`
  - `npm run lint`
  - `npm test`
  - `npm run build`
  - `npm run rebuild:native`
  - `npm run package:win`
- [ ] 加入 `SOURCE_MANIFEST.md` 与 `THIRD_PARTY_NOTICES.md`。
- [ ] 验证 Windows 打包产物可生成。
- [ ] 2F 验收标准：
  - `auto_send` 默认禁用；
  - 发送逻辑只经 mock 测试；
  - 原生模块可 rebuild；
  - Windows 包可生成。

---

## Cross-Phase Acceptance Checklist

- [ ] Go RPA 未恢复
- [ ] 未直接复制 `input-utils.ts`
- [ ] token 不进 stdout/日志/文件
- [ ] `RegionProfileV2` 只以 `normalizedToClient` 为权威坐标
- [ ] `idempotencyKey + requestDigest + perWindowTaskLock` 已落实
- [ ] `paste_only` 与 `auto_send` 完全分离
- [ ] Provider Hub 首版仅支持本地 provider
- [ ] 日志脱敏
- [ ] `SOURCE_MANIFEST.md` / `THIRD_PARTY_NOTICES.md` 已维护

---

## Verification Commands Summary

### Python

```bash
uv run pytest C:\Users\33031\Desktop\bot\tests\unit_tests\desktop_automation\ -q
```

### Runtime

```bash
npm run typecheck
npm run lint
npm test
npm run build
npm run rebuild:native
npm run package:win
```

---

## Execution Gate

本计划已按 2A～2F 分段，并包含强制门禁：

- 2A 通过后才能进入 2B
- 2B 通过后才能进入 2C
- **2C 实机 `paste_only` 通过之前，禁止进入 2D～2F**

在你明确确认前，不进入实施。
