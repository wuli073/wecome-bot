# RPA Phase 2 Design: Electron + TypeScript Desktop Runtime Integration

## Status

- Date: 2026-06-29
- Phase: 2 design only
- Implementation status: not started
- Code changes in this phase: documentation only

## Goal

将 `sightflow-desktop-agent` 的桌面 RPA 能力选择性迁移到当前项目，构建一个**独立的、无主界面的 Electron + TypeScript Runtime**，由 Python 后端托管，用于窗口发现、窗口绑定、区域校准、截图、视觉验证、`paste_only`、受控 `auto_send`、会话搜索与相关桌面自动化任务。

## Explicit Non-Goals

1. 不恢复任何 Go RPA。
2. 不完整复制 SightFlow 项目。
3. 不直接复制巨型 `input-utils.ts`。
4. 不修改当前业务代码。
5. 不进入实施。
6. 不 commit，不 push。

---

## 1. 来源仓库、分支、Commit、授权与归属

### 1.1 来源快照

- Source repository: [sightflow-dev/sightflow-desktop-agent](https://github.com/sightflow-dev/sightflow-desktop-agent)
- Source branch inspected: `main`
- Source commit inspected: `8bbc196ac372c9365f732bf8eb9d6fb83b3eb5e3`
- Source local inspection path: `C:\Users\33031\Desktop\.tmp-sightflow-agent`

### 1.2 授权

根据来源仓库的 `package.json`、`LICENSE`、`NOTICE`：

- License: `Apache-2.0`
- Copyright notice:
  - `Copyright 2026 SightFlow Team (sightflow.dev)`

### 1.3 归属与许可证落地

Phase 2 落地时新增：

```text
apps/desktop-rpa-runtime/SOURCE_MANIFEST.md
apps/desktop-rpa-runtime/THIRD_PARTY_NOTICES.md
```

其中记录：

- 来源仓库；
- 来源 commit；
- 原始文件路径；
- 目标文件路径；
- `direct copy` / `modified` / `rewritten`；
- Apache-2.0 归因；
- 修改声明。

规则：

1. 只有**存在实质复制或改写上游代码**的目标文件，才在 `SOURCE_MANIFEST.md` 中登记为 direct copy / modified。
2. 对于**完全重写、仅借鉴设计思路**的文件，不机械附加上游版权头，只在清单中记录“rewritten from concepts”.
3. 二进制分发时保留 Apache-2.0 必需归因与 notices。

---

## 2. 迁移范围：直接迁移 / 拆分重构 / 不迁移

原则：

- 迁移的是 **Runtime 内核能力**，不是 SightFlow 整体产品。
- 当前项目已有 Python 后端、HTTP API 和 Web 前端，因此 Electron Runtime 仅承担“本机桌面执行器”职责。
- 不直接复制 `input-utils.ts`，必须拆分。

### 2.1 可直接迁移（允许小幅适配）

| 来源文件 | 迁移方式 | 目标职责 |
|---|---|---|
| `src/core/ai-client.ts` | 精简迁移 | OpenAI-compatible vision client 基础能力 |
| `src/core/runtime-host.ts` | 结构迁移 | Runtime 内部任务调度 Host |
| `src/core/session-types.ts` | 类型迁移 | Runtime/Provider/Task 类型契约 |
| `src/main/provider-bundle.ts` | 精简迁移 | 本地 provider bundle 加载 |
| `src/core/rpa/types.ts` | 迁移并重命名 | 坐标/显示器/区域基础类型 |
| `src/core/rpa/image-compare.ts` | 基本迁移 | 截图 diff / pixel compare |
| `src/main/overlay-window.ts` | 提炼后迁移 | Overlay 框选与多显示器坐标换算 |

### 2.2 必须拆分重构后迁移

| 来源文件 | 问题 | 迁移策略 |
|---|---|---|
| `src/core/rpa/input-utils.ts` | 鼠标、剪贴板、粘贴、发送全部耦合 | 拆为 `mouse-controller` / `click-safety` / `clipboard-controller` / `paste-controller` / `send-controller` |
| `src/core/rpa/window-utils.ts` | 窗口发现、截图缓存、应用特判混在一起 | 拆为 `window-finder` / `window-binder` / `display-metrics` |
| `src/core/rpa/screenshot-utils.ts` | 窗口截图、区域截图、红点分析混合 | 拆为 `capture-service` / `region-screenshot` / `image-analysis` |
| `src/core/rpa/vision-utils.ts` | prompt、bbox 解析、cache 混合 | 拆为 `vision-client` / `bbox-parser` / `layout-detector` |
| `src/core/rpa/has-unread.ts` | 红点检测与 WeChat/WeCom prompt 深耦合 | 重构为 `red-dot-detector` + `unread-detector` |
| `src/core/generic-channel-session.ts` | 带有 SightFlow 产品级会话轮询语义 | 只借鉴状态机，不原样迁移 |
| `src/core/box-select-device.ts` | 面向 SightFlow 单机聊天流程 | 只复用框选区域思想与截图入口思路 |

### 2.3 不迁移

| 来源内容 | 不迁移原因 |
|---|---|
| `src/renderer/src/App.tsx` 等主 UI | 当前目标是无主界面 Runtime |
| `src/renderer/src/MemoryWindow.tsx` | 与工作记忆产品强绑定 |
| `src/core/memory/*` | 当前项目不建设 SightFlow Memory |
| `src/core/trace/*` | 当前项目已有自己的 run/persistence 体系 |
| `src/main/skill-server.ts` | 与当前项目无关 |
| 远程 provider marketplace | 首版 Provider Hub 不支持运行时远程下载 |
| 整个 SightFlow 打包与品牌资源 | 避免不完整复制整个项目 |

---

## 3. 新目录结构

```text
apps/desktop-rpa-runtime/
  package.json
  package-lock.json
  tsconfig.json
  electron.vite.config.ts
  electron-builder.yml
  README.md
  SOURCE_MANIFEST.md
  THIRD_PARTY_NOTICES.md
  src/
    main/
      index.ts
      bootstrap/
        runtime-app.ts
        single-instance.ts
        handshake.ts
      api/
        local-http-server.ts
        auth.ts
        routes-health.ts
        routes-runtime.ts
        routes-calibration.ts
        routes-actions.ts
      runtime/
        runtime-host.ts
        task-runner.ts
        task-registry.ts
        task-locks.ts
        state-store.ts
      window/
        window-finder.ts
        window-activator.ts
        window-binder.ts
        window-validator.ts
        display-metrics.ts
      capture/
        capture-service.ts
        window-screenshot.ts
        region-screenshot.ts
        dpi-transform.ts
      overlay/
        overlay-window.ts
        overlay-session.ts
        overlay-validator.ts
      input/
        mouse-controller.ts
        click-safety.ts
        clipboard-controller.ts
        paste-controller.ts
        send-controller.ts
      vision/
        ai-client.ts
        provider-hub.ts
        provider-bundle.ts
        bbox-parser.ts
        layout-detector.ts
        red-dot-detector.ts
        message-diff.ts
        session-verifier.ts
      domain/
        region-profile.ts
        runtime-types.ts
        task-types.ts
        error-types.ts
        clipboard-types.ts
    preload/
      index.ts
    renderer/
      overlay.html
      overlay.tsx
      overlay.css
  resources/
    providers/
      builtin/
```

说明：

- 只有 overlay renderer，没有主界面。
- Python 与 Runtime 只通过本地 HTTP/JSON 通信。
- 首版 Provider Hub 只允许内置本地 provider 与显式配置的本地 provider。

---

## 4. Runtime 握手、密钥、启动、鉴权、健康检查、通信

## 4.1 启动与握手模型

Phase 2 固定为：

```text
Python 生成高熵 token
→ 通过环境变量或受控 stdin 传入 Runtime
→ Runtime 监听 127.0.0.1:0
→ stdout 仅返回 pid/port/protocolVersion/runtimeVersion
```

### 4.1.1 强约束

1. token 不通过命令行参数传递；
2. token 不写入 stdout；
3. token 不写入日志；
4. token 不写入状态文件；
5. Phase 2 不使用 `runtime-info.json` 兜底；
6. Python 进程内保存连接信息；
7. Runtime 退出后 token 立即失效。

### 4.1.2 推荐实现

- Python 启动 Electron 子进程；
- Python 在启动前生成高熵 bearer token；
- Python 通过：
  - 环境变量，或
  - 受控 stdin 握手输入
  传给 Runtime；
- Runtime 启动本地 HTTP server，监听 `127.0.0.1:0`；
- Runtime 获取实际绑定端口后，仅在 stdout 单行输出：

```json
{
  "pid": 12345,
  "port": 42177,
  "protocolVersion": "2",
  "runtimeVersion": "0.1.0"
}
```

Python 保存：

```text
pid
host=127.0.0.1
port
protocolVersion
runtimeVersion
token
```

## 4.2 鉴权

仅接受：

```text
Authorization: Bearer <token>
```

规则：

1. token 由 Python 生成；
2. token 仅在当前 Runtime 生命周期内有效；
3. Runtime 内存中持有 token，不落盘；
4. token 与当前 Runtime 进程强绑定；
5. Runtime 退出后，旧 token 全部失效。

## 4.3 健康检查

### `GET /healthz`

返回：

- `status`: `starting | ready | degraded | stopping`
- `protocolVersion`
- `runtimeVersion`
- `uptimeMs`

### `GET /v1/runtime/status`

返回：

- `windowingAvailable`
- `captureAvailable`
- `inputAvailable`
- `providerHubReady`
- `activeTaskCount`
- `lastErrorCode`
- `displaySummary`

Python 行为：

1. 启动后轮询 `/healthz` 直到 `ready`；
2. 超时则返回 `RPA_RUNTIME_UNAVAILABLE`；
3. 所有业务任务前做一次轻量 status 校验。

## 4.4 通信方式

Phase 2 采用：

- Python ↔ Runtime: HTTP/JSON
- Overlay ↔ Main: Electron IPC

不使用 WebSocket 作为主协议。

原因：

- 当前 Python 服务层是 request/response 模式；
- `/paste-draft`、校准、搜索、诊断都更适合 HTTP 命令式 API；
- 更利于 mock、集成测试、重试与幂等控制。

---

## 5. 窗口发现、激活、绑定、失效验证、多显示器与 DPI

## 5.1 WindowDescriptor

运行时窗口发现输出：

```text
WindowDescriptor = {
  windowId,
  title,
  executablePath,
  processName,
  processId,
  displayId,
  boundsLogical,
  scaleFactor,
  isVisible,
  isMinimized
}
```

发现来源：

- Windows: `node-window-manager`
- 当前前台窗口: `active-win`
- 显示器信息: Electron `screen`

## 5.2 窗口激活

激活流程：

1. 窗口仍存在；
2. 如已最小化则 restore；
3. bring-to-front / focus；
4. 激活后重新抓取一次 display 与 client bounds；
5. 激活失败则 fail-closed。

错误码：

- `WINDOW_NOT_FOUND`
- `WINDOW_NOT_VISIBLE`
- `WINDOW_ACTIVATION_FAILED`

## 5.3 WindowBinding 加强模型

```text
WindowBinding = {
  executablePath,
  processName,
  processId,
  windowId,
  titleHint,
  displayId,
  clientBounds,
  validatedAt
}
```

规则：

1. `windowId` / `processId` 仅是当前运行期标识，不作为跨重启永久身份；
2. 跨重启优先使用 `executablePath + processName + appType` 重新发现；
3. 找到多个候选窗口时阻断，不自动选择；
4. 每次点击、截图、粘贴前重新验证前台窗口和绑定。

## 5.4 绑定与重新发现

绑定来源：

- 人工校准时选中的窗口；
- 或后端传入的目标窗口约束。

重新发现优先级：

1. 当前 `windowId/processId` 是否仍有效；
2. 若失效，按 `executablePath + processName + appType` 重新发现；
3. 若多个候选同时匹配，返回：
   - `WINDOW_CANDIDATE_AMBIGUOUS`
4. 若无候选，返回：
   - `WINDOW_BINDING_INVALID`

## 5.5 失效验证

在每次截图、点击、粘贴、发送前验证：

1. 绑定窗口仍存在；
2. 前台窗口仍为目标窗口；
3. `clientBounds` 与当前窗口 client bounds 未发生不可接受偏移；
4. 当前 display 与 profile 基线可兼容；
5. 会话标题区域仍可验证为目标会话。

失败则返回：

- `WINDOW_BINDING_INVALID`
- `WINDOW_FOCUS_LOST`
- `REGION_PROFILE_INVALID`
- `CONVERSATION_VALIDATION_FAILED`

## 5.6 多显示器与 DPI

要求：

1. Runtime 内部统一以 **logical coordinates** 表达区域；
2. Profile 只持久化 client-relative 归一化区域；
3. 所有 screen/window/client rect 只在运行时推导；
4. Overlay 校准时要求全部区域位于同一 display；
5. 窗口跨显示器移动后允许重算，但若缩放变化过大则要求重新校准。

---

## 6. RegionProfileV2：唯一权威坐标模型

## 6.1 权威来源

唯一持久化权威坐标：

```text
normalizedToClient
```

只额外保存校准基线：

```text
clientSizeLogical
clientSizePhysical
displayId
scaleFactor
capturedAt
```

禁止把以下内容作为并列持久化真值：

- `screenRectLogical`
- `windowRectLogical`
- `clientRectLogical`

这些值只能在运行时计算，或作为诊断结果返回，不能作为长期持久化权威来源。

## 6.2 Profile 结构

```json
{
  "schemaVersion": 2,
  "appType": "wework",
  "connectorId": "connector-123",
  "baseline": {
    "clientSizeLogical": { "width": 1280, "height": 820 },
    "clientSizePhysical": { "width": 1600, "height": 1025 },
    "displayId": 1,
    "scaleFactor": 1.25,
    "capturedAt": "2026-06-29T00:00:00Z"
  },
  "regions": {
    "conversationList": {
      "normalizedToClient": { "x": 0.00, "y": 0.08, "width": 0.26, "height": 0.92 }
    },
    "chatHeader": {
      "normalizedToClient": { "x": 0.26, "y": 0.00, "width": 0.74, "height": 0.08 }
    },
    "chatHistory": {
      "normalizedToClient": { "x": 0.26, "y": 0.08, "width": 0.74, "height": 0.68 }
    },
    "inputBox": {
      "normalizedToClient": { "x": 0.26, "y": 0.76, "width": 0.74, "height": 0.24 }
    },
    "searchBox": {
      "normalizedToClient": { "x": 0.03, "y": 0.02, "width": 0.20, "height": 0.05 }
    }
  },
  "inputSafePoints": [
    { "xRatio": 0.18, "yRatio": 0.72 },
    { "xRatio": 0.24, "yRatio": 0.68 }
  ]
}
```

## 6.3 不兼容旧 Go profile

Phase 2 明确：

- `schemaVersion = 2`
- 不兼容旧 Go profile
- 不做旧字段自动迁移

拒绝旧字段：

- `conversationTitleRegion`
- `messageInputRegion`
- `windowClassHash`
- 旧 client-relative 兼容结构

错误码：

- `REGION_PROFILE_SCHEMA_UNSUPPORTED`

---

## 7. 框选区域、输入框安全点、`paste_only`、剪贴板边界

## 7.1 区域语义

```text
RegionProfileV2.regions = {
  conversationList,
  chatHeader,
  chatHistory,
  inputBox,
  sendButton?: optional,
  searchBox?: optional,
  unreadBadgeLane?: optional
}
```

## 7.2 输入框安全点

安全点是 `inputBox` 内的**可编辑区域候选点**，不是输入框中心点。

```text
InputSafePoint = {
  xRatio,
  yRatio,
  minInsetPx
}
```

约束：

1. 必须远离边缘、工具栏、表情区、附件区；
2. 运行时根据当前 client bounds 推导实际点位；
3. 只能在可编辑区域内使用。

## 7.3 剪贴板能力边界

首版明确支持并恢复：

```text
text
html
rtf
image
```

如果检测到：

- 文件列表，或
- 无法可靠恢复的自定义格式

则在覆盖剪贴板前 fail-closed，返回：

```text
CLIPBOARD_FORMAT_UNSUPPORTED
```

禁止出现：

```text
先覆盖剪贴板
→ 后发现无法恢复
```

后续若引入 Win32 原生 clipboard snapshot，再扩展文件列表和自定义格式。

## 7.4 剪贴板恢复失败

恢复失败不得静默记为普通成功。

必须返回：

```text
status = succeeded_with_warning
clipboardRestoreFailed = true
```

并要求前端明确提示。

## 7.5 `paste_only` 行为

定义：

- 仅粘贴 draft；
- 不按 Enter；
- 不点发送按钮；
- 不变更业务语义为已发送。

### 粘贴后验证

粘贴后必须验证输入区发生预期变化。

若需要备选安全点重试，每次都必须重新验证：

1. 目标窗口仍是前台；
2. 窗口绑定未变化；
3. 当前会话仍可信；
4. 安全点仍位于 `inputBox editable area`。

最多重试一次，不得无限换点。

失败时返回结构化错误：

- `INPUT_FOCUS_FAILED`
- `PASTE_NOT_OBSERVED`
- `WINDOW_FOCUS_LOST`
- `REGION_PROFILE_INVALID`

---

## 8. 并发、幂等、任务状态

Runtime 必须支持：

```text
idempotencyKey
requestDigest
perWindowTaskLock
```

## 8.1 并发锁

规则：

1. 同一目标窗口同一时间只能执行一个输入类任务；
2. 以下任务互斥：
   - calibration
   - paste
   - send
   - conversation-search
3. 锁粒度为 `perWindowTaskLock`；
4. 没拿到锁时任务进入 `queued` 或直接返回已有运行任务。

## 8.2 幂等

规则：

1. Python 重试不得造成重复粘贴或重复发送；
2. 相同 `idempotencyKey` 返回已有任务；
3. 不同草稿内容必须生成不同 `requestDigest`；
4. `requestDigest` 必须覆盖：
   - botId
   - connectorId
   - action
   - draftId
   - draftText hash
   - sendStrategy（如有）
   - target conversation identity

## 8.3 任务状态

至少包括：

```text
queued
running
succeeded
succeeded_with_warning
blocked
failed
cancelled
timed_out
```

---

## 9. VLM、截图、红点、diff、会话搜索、引用回复、历史搜索、会话验证

## 9.1 VLM 职责

VLM 只承担辅助视觉职责：

1. 布局识别；
2. 会话标题验证；
3. 搜索结果匹配验证；
4. 引用回复入口定位；
5. 粘贴后输入区变化的辅助确认。

## 9.2 截图类型

- `windowScreenshot`
- `regionScreenshot`
- `fullDisplayScreenshot`

统一返回：

- `pngBase64`
- `displayId`
- `scaleFactor`
- `boundsLogical`
- `capturedAt`

## 9.3 红点检测

双路径：

1. 像素法优先；
2. VLM 兜底。

## 9.4 消息 diff

用于：

- 粘贴后输入区变化检测；
- 会话切换后聊天区变化检测；
- 新消息到达前后差异验证。

## 9.5 会话搜索

流程：

1. 激活搜索框；
2. 粘贴目标会话名；
3. 等待结果；
4. 验证匹配；
5. 点击候选；
6. **再次验证会话**；
7. 通过后才允许后续粘贴。

若候选不唯一：

- `CONVERSATION_AMBIGUOUS`

不允许继续执行。

## 9.6 引用回复

作为增强能力保留接口，不要求首批全部落地。

执行前仍必须做会话验证。

## 9.7 历史搜索

历史搜索与会话搜索分离。

在 history-search 前必须验证：

- 当前窗口绑定；
- 当前会话可信；
- 标题区域匹配期望会话。

## 9.8 会话验证

在以下动作前强制执行：

- paste
- send
- quote
- history-search

至少支持：

```text
会话标题区域截图
期望会话名称
视觉匹配结果
窗口绑定
```

自动搜索并切换会话后，必须再次验证，不能因为点击了搜索结果第一项就直接粘贴。

---

## 10. Provider Hub、AIClient、RuntimeHost、日志边界

## 10.1 Provider Hub 首版范围

首版只允许：

```text
内置本地 provider
显式配置的本地 provider
```

暂不支持：

- 运行时下载远程 manifest；
- 任意远程 bundle 加载；
- marketplace 风格动态安装。

## 10.2 AIClient

保留为 OpenAI-compatible 基础能力，但拆为：

- `BaseAIClient`
- `VisionAIClient`

首版重点是 `VisionAIClient`。

## 10.3 RuntimeHost

`RuntimeHost` 是 Runtime 内部统一编排器：

```text
RuntimeHost
  -> TaskRunner
  -> WindowBinder
  -> CaptureService
  -> SessionVerifier
  -> PasteController
  -> SendController
```

## 10.4 日志脱敏

以下内容不得写入日志：

- API Key
- token
- draftText
- 截图内容

日志仅记录：

```text
taskId
requestDigest
providerId
stage
duration
errorCode
```

---

## 11. `paste_only` 与 `auto_send` 分离，且发送默认禁用

## 11.1 模式定义

### `paste_only`

- 只粘贴，不发送。

### `auto_send`

- 在粘贴成功且发送路径被明确授权时发送。

## 11.2 发送策略

发送策略必须单选：

```text
enter
ctrl_enter
click_send_button
```

不得失败后自动尝试其他策略。

## 11.3 `auto_send` 首版运行约束

首版保持：

- 编译完成；
- 运行时默认禁用。

只有同时满足以下条件才允许发送：

```text
前端明确动作
Python 明确授权
Runtime 配置开启
会话验证通过
窗口绑定通过
草稿 digest 匹配
```

## 11.4 自动发送测试边界

设计修正为：

```text
单元测试和集成测试仅使用 mock input driver
```

未经用户后续单独明确批准，不做真实 `Enter`、`Ctrl+Enter` 或点击发送按钮的实机测试。

---

## 12. Python、前端与现有 `/paste-draft` 的接入方式

## 12.1 Python 侧职责

当前已有对接壳层：

- `src/langbot/pkg/desktop_automation/service.py`
- `src/langbot/pkg/desktop_automation/runtime_process.py`
- `src/langbot/pkg/desktop_automation/client.py`
- `src/langbot/pkg/desktop_automation/repository.py`

Phase 2 实施时，Python 负责：

1. 启动 Runtime；
2. 注入 token；
3. 读取 stdout 握手结果；
4. 保存内存态连接信息；
5. 调用 Runtime HTTP API；
6. 管理 `DesktopAutomationRun`；
7. 管理 `RegionProfileV2`。

Python 不负责：

1. 直接桌面输入；
2. 截图裁剪；
3. VLM prompt 执行。

## 12.2 前端职责

前端继续只调用后端。

前端要点：

1. 区分“仅粘贴”和“自动发送”；
2. 展示 Runtime 状态；
3. 展示 `schemaVersion=2` 校准状态；
4. 展示 `succeeded_with_warning`，尤其是 `clipboardRestoreFailed=true`。

## 12.3 现有 `/paste-draft`

保留现有业务入口：

```text
POST /api/v1/bots/{bot_id}/messages/{message_id}/paste-draft
```

但语义固定为：

- 永远只粘贴；
- 永远不发送。

建议后端内部流程：

1. 校验 bot / message / draft；
2. 校验 Runtime ready；
3. 校验 `RegionProfileV2`；
4. 构造 `idempotencyKey` 与 `requestDigest`；
5. 创建或复用 `DesktopAutomationRun(action='paste_draft', execution_mode='paste_only')`；
6. 调 Runtime `POST /v1/tasks/paste-draft`；
7. 按 task status 更新 run。

## 12.4 `/send-draft`

保留现有业务入口，但：

- 必须独立于 `/paste-draft`；
- 默认禁用；
- 只能走显式发送策略。

---

## 13. 测试、打包、工具链固定

## 13.1 单元测试

Runtime TypeScript 单元测试覆盖：

- bbox/point parser
- DPI transform
- logical/physical coordinate conversion
- RegionProfileV2 schema validation
- input safe point 计算
- clipboard snapshot/restore
- diff threshold
- red-dot detector
- task idempotency / digest
- perWindowTaskLock

## 13.2 集成测试

Python ↔ Runtime 集成测试覆盖：

- 启动握手
- token 鉴权
- `/healthz`
- `/v1/runtime/status`
- `paste-draft`
- `cancel`
- 幂等复用
- clipboard unsupported
- window ambiguous / conversation ambiguous

发送相关集成测试仅使用 mock input driver。

## 13.3 实机测试

实机测试只覆盖：

- 2B：窗口发现/绑定/DPI/Overlay
- 2C：`paste_only`

在 2C 的真实 `paste_only` 未通过前：

- 禁止进入 2D～2F

未经用户后续单独明确批准，不做真实发送实机测试。

## 13.4 工具链固定

新 Runtime 独立使用 `npm`，固定：

```text
Node 22 LTS
Electron 精确版本
package-lock.json
原生依赖精确版本
```

必须提供：

```text
npm run typecheck
npm run lint
npm test
npm run build
npm run rebuild:native
npm run package:win
```

禁止依赖全局安装的：

- Electron
- node-gyp
- 任意 native module

---

## 14. 迁移风险、原生模块 rebuild、Windows 分发

主要风险：

1. 原生模块 ABI 兼容：
   - `@hurdlegroup/robotjs`
   - `node-window-manager`
   - `active-win`
2. 多显示器 / DPI 漂移；
3. 前台激活失败；
4. profile 失效；
5. 剪贴板格式恢复边界；
6. Windows Defender / SmartScreen 分发影响。

### 原生模块 rebuild

必须支持：

- `electron-builder install-app-deps`
- `npm run rebuild:native`

### Windows 分发

建议分两阶段：

#### 开发/内测

- portable unpacked 目录

#### 正式分发

- NSIS 安装包

自动发现优先级：

1. 明确配置路径；
2. 安装目录探测；
3. PATH 探测。

失败则统一：

- `RPA_RUNTIME_NOT_AVAILABLE`

---

## 15. Runtime HTTP API 草案

### 健康与状态

- `GET /healthz`
- `GET /v1/runtime/status`

### 校准

- `POST /v1/calibration-sessions`
- `GET /v1/calibration-sessions/{id}`
- `POST /v1/calibration-sessions/{id}/cancel`

### 任务

- `POST /v1/tasks/paste-draft`
- `POST /v1/tasks/send-draft`
- `POST /v1/tasks/conversation-search`
- `POST /v1/tasks/history-search`
- `POST /v1/tasks/quote-reply`
- `POST /v1/tasks/diagnose`
- `GET /v1/tasks/{id}`
- `POST /v1/tasks/{id}/cancel`

### 诊断

- `POST /v1/debug/find-window`
- `POST /v1/debug/capture-region`

---

## 16. 分段实施边界（设计级）

阶段二实施必须拆为：

```text
2A Runtime 骨架、鉴权、health、Python 托管
2B 窗口发现、绑定、DPI、Overlay、RegionProfileV2
2C safe typing zone、剪贴板、paste_only
2D 截图、diff、红点、VLM
2E 会话搜索、历史搜索、引用回复
2F auto_send、打包和分发
```

规则：

1. 每段必须独立验收；
2. 上一段未通过不得进入下一段；
3. 2C 实机 `paste_only` 未通过之前，禁止进入 2D～2F。

---

## 17. 结论

Phase 2 的正确方向不是把 SightFlow 整个 Electron 产品搬进来，而是：

1. 以 `sightflow-desktop-agent@8bbc196ac372c9365f732bf8eb9d6fb83b3eb5e3` 为能力来源；
2. 只迁移与桌面 RPA Runtime 直接相关的 TypeScript/Electron 内核；
3. 构建一个由 Python 主控、无主界面、本地 HTTP 鉴权、可独立打包的桌面执行器；
4. 以 `RegionProfile schemaVersion=2` 切断旧 Go profile 兼容包袱；
5. 强制分离 `paste_only` 与 `auto_send`，并保持自动发送首版运行时默认禁用；
6. 通过 `idempotencyKey + requestDigest + perWindowTaskLock` 保证互斥、幂等与可审计；
7. 通过会话验证、剪贴板边界、日志脱敏与分段验收降低集成风险。

这是一条最小侵入、边界清晰、可分段验收、且与当前项目架构最匹配的路线。
