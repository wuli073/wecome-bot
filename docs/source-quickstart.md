# Windows 源码运行快速开始

此流程仅运行 GitHub 源码：不使用 Launcher、Portable、Installer，也不会构建安装包。

## 前置条件

- Windows x64
- Git
- Node.js **22.x**（含 npm）
- [uv](https://docs.astral.sh/uv/)

脚本使用 `uv.lock` 和 `web/package-lock.json` 进行冻结安装；不会升级依赖或改写 lock 文件。

## Windows 源码分发

Windows 源码分发包中的脚本按顺序使用：

1. `01-check-environment.bat` 检查 Windows x64、PowerShell、WinGet、Git、Node.js 22、npm、uv 和 GitHub 连通性。缺少 Git、Node.js 22 或 uv 时，会汇总缺失项；确认后使用 WinGet 安装。npm 随 Node.js 安装，脚本不会单独安装 npm。缺少 WinGet 时，请先从 Microsoft Store 安装或更新 App Installer 后重新运行 01。Windows 架构、PowerShell 或网络问题仍需自行处理。
2. `02-install-wecome-bot.bat` 只负责拉取或更新项目，并安装项目内部依赖。它会由 `uv` 自动下载和管理 Python 3.12；不需要预装系统 Python，已安装的 Python 3.14 也不会影响安装。首次准备受管 Python 3.12 需要网络并可能多花一些时间。
3. `03-start-wecome-bot.bat` 只负责启动项目。

分发包中的 BAT 文件使用 UTF-8 无 BOM 和 CRLF 行尾；第一行保持为 `@echo off`，第二行执行 `chcp 65001 >nul`，以避免 BOM 影响 cmd.exe 解析首条命令。

## Clone 与 checkout

```powershell
git clone https://github.com/wuli073/wecome-bot.git
Set-Location wecome-bot
git checkout <branch-or-tag>
```

## 安装依赖

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-source.ps1
```

该命令先运行 `uv python install 3.12`，再运行 `uv sync --frozen --dev --python 3.12 --managed-python` 和 `npm ci`。`.venv` 固定使用 Python 3.12，并在安装后验证 Python 版本及 `onnxruntime` 导入。它不会创建或覆盖 `web/.env`。

无需修改系统 PATH，也无需卸载 Python 3.14。若看到 `onnxruntime` 或 `cp314` 安装错误，说明仍在使用旧版安装脚本；更新后重新运行 `02-install-wecome-bot.bat`。

## 启动

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-source.ps1
```

脚本启动源码 Backend（默认 `5300`）和 Vite Web（默认 `3000`），等待 `/healthz`、`/api/v1/system/runtime/status`、`/readyz` 全部就绪后打开浏览器。输出中包含 PID、端口、日志和独立用户数据目录。

默认用户数据目录为 `.tmp\source-runtime\user-data`，不会使用仓库的 `data/`，也不会写入浏览器、微信或企业微信的现有资料。可为并行或临时运行指定独立目录和端口：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-source.ps1 `
  -UserDataRoot "$env:TEMP\wecome-source" -BackendPort 55300 -WebPort 55301
```

真实发送默认关闭：`LANGBOT_RPA_FORCE_DISABLE_SEND=1`、`LANGBOT_RPA_ALLOW_AUTO_SEND=0`、`LANGBOT_BROADCAST_SEND_ENABLED=0`。源码脚本不提供打开真实发送的参数。

## 停止

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-source.ps1
```

停止脚本只读取该次源码启动写入的状态文件，并以 PID、启动时间和仓库命令行验证所有权后停止其进程树；不会按 `python` 或 `node` 进程名批量结束系统进程。使用了自定义用户数据目录时，传入同一个 `-UserDataRoot`。

## 诊断

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\doctor-source.ps1
```

Doctor 检查版本和冻结依赖、端口、health/runtime/ready、平台列表、`wechat-decrypt` 源码入口、企业微信 MCP/Worker 状态，以及群发配置 API。`wxwork-local` 未完成企业微信数据库配置时会显示 `warn`，而不是把“尚未配置”误判为启动失败。

## 更新源码

先停止运行中的源码栈，再更新并按 lock 重新安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\stop-source.ps1
git fetch --tags origin
git checkout <branch-or-tag>
git pull --ff-only
powershell -ExecutionPolicy Bypass -File .\scripts\setup-source.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\start-source.ps1
```

若保留默认 `.tmp` 用户数据，升级源码不会删除其中的本地设置；需要全新实例时指定新的 `-UserDataRoot`。

## 日志

默认日志目录：`.tmp\source-runtime\user-data\logs\source`

- `backend.stdout.log` / `backend.stderr.log`：源码 Backend
- `web.stdout.log` / `web.stderr.log`：Vite Web
- `data\logs\`：应用日志
- `connectors\wxwork-local\logs\`：企业微信 MCP Worker（配置后）

## 源码功能烟测

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test-source-smoke.ps1
```

烟测创建临时用户数据，验证平台列表、向导 progress/completed、企业微信 MCP Worker 源码入口与基础监听、群发 scope/group field 保存，以及停止后端口和进程树清理。它不连接真实企业微信数据，也不发送消息。

## 常见问题

### `Node.js 22.x is required`

安装 Node.js 22 LTS，重新打开 PowerShell，并确认 `node --version` 输出为 `v22.*`。

### 端口已被占用

先运行 `stop-source.ps1`。如果端口属于其他程序，停止该程序或使用 `-BackendPort`、`-WebPort` 指定空闲端口；不要通过结束所有 Python/Node 进程解决。

### `readyz` 超时

运行 `doctor-source.ps1`，然后查看 `backend.stderr.log` 和 `data\logs\`。首次启动会创建独立数据库、执行迁移并初始化可选运行时，耗时通常更长。

### 企业微信 MCP Worker 未启动

先完成企业微信数据库连接器配置。`doctor-source.ps1` 会检查 `vendor\wechat_decrypt\mcp_wxwork_http_server.py`、Worker 状态文件及 5681 端口。未配置企业微信客户端/数据库时，Worker 显示为 `not_configured` 是预期状态。

### 群发接口返回 `BROADCAST_SCOPE_REQUIRED`

群发请求必须使用已绑定的 `wxwork_database` bot UUID 和 `wxwork-local` connector ID。烟测覆盖了该绑定与 `group_field` 的保存路径。

## 第三方代码与敏感数据

`vendor/wechat_decrypt/VENDOR_SOURCE.json` 记录了 `wechat-decrypt` 的上游来源和快照提交。该目录当前没有单独的许可证文本；在重新分发该第三方源码前，应根据该 provenance 到上游仓库核对并纳入适用许可证。不要提交 `.env`、用户数据目录、`data/`、日志、数据库、Token、密码、浏览器资料或企业微信资料。
