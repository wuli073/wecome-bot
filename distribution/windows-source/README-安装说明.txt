# Wecome Bot Windows Source Starter 安装说明

## 系统要求

- Windows 10 或 Windows 11 x64。
- 可以访问 GitHub。
- PowerShell 5.1 或更高版本。
- 建议使用普通用户账户运行。
- 不需要安装 Visual Studio 或 C++ Build Tools。
- 仍需要 Git、Node.js 22、npm 和 uv。`01-check-environment.bat` 会检查这些依赖，并在缺少 Git、Node.js 22 或 uv 时使用 winget 安装。

Desktop Runtime 使用已验证的固定预构建 Release 包，不需要 C++ Build Tools。

## 安装步骤

1. 解压整个 Starter ZIP，保持四个文件位于同一目录。
2. 运行 `01-check-environment.bat`。
3. 环境检查成功后运行 `02-install-wecome-bot.bat`。
4. 默认安装目录为：

```text
%USERPROFILE%\wecome-bot
```

5. 自定义安装目录示例：

```bat
02-install-wecome-bot.bat "D:\Apps\Wecome Bot"
```

6. 安装完成后，在安装目录中运行：

```text
03-start-wecome-bot.bat
```

## 默认真实发送说明

本发行版默认启用真实发送能力、自动发送和群发，并默认允许已接入的 Connector。配置真实账号、Connector、群组或联系人后，相关操作可能向外部聊天软件实际发送消息。正式使用前应核对账号、目标和消息内容。

该提示仅作说明，不阻断启动。

## 更新方式

在安装目录重新运行：

```text
02-install-wecome-bot.bat
```

安装程序会检查工作区、对 main 执行 fast-forward 更新、更新依赖，并校验及安装固定预构建 Desktop Runtime。

## 日志位置

- `runtime\logs\setup-source-transcript.log`
- `.tmp\source-runtime\user-data\logs\source`

## 停止服务

在安装目录执行：

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-source.ps1 -Action Stop
```

## 常见问题

### 无法访问 GitHub

检查网络、代理、TLS 和 GitHub 访问权限后重新运行环境检查。

### winget 不存在

从 Microsoft Store 安装或更新“应用安装程序（App Installer）”，然后重新运行环境检查。

### Node.js 不是 22.x、npm 缺失或 uv 缺失

运行 `01-check-environment.bat`。若 Node.js 已存在但版本不是 22.x，请调整 PATH、NVM 或 shim 优先级后重试。

### Runtime 下载中断或 SHA 校验失败

重新运行 `02-install-wecome-bot.bat`。安装程序只接受固定 Release 的已验证预构建 Runtime；请检查网络后重试。

### 端口被占用

停止当前服务，或确认 3000 和后端所需端口没有被其他程序占用，然后重新启动。

### 工作区存在用户修改，更新被拒绝

请处理或提交安装目录中的修改后重新运行安装程序。安装程序不会删除安装目录。

### 查看日志

安装日志位于 `runtime\logs\setup-source-transcript.log`；运行日志位于 `.tmp\source-runtime\user-data\logs\source`。
