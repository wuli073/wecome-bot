using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Globalization;
using System.Windows.Forms;

namespace ChatbotLauncher;

internal static class Program
{
    [STAThread]
    private static int Main()
    {
        ApplicationConfiguration.Initialize();
        LauncherSingleInstanceGuard? singleInstance = null;
        LauncherInstallationLayout? layout = null;
        try
        {
            var installRoot = Path.GetFullPath(AppContext.BaseDirectory);
            var verificationUserDataRoot = Environment.GetEnvironmentVariable("CHATBOT_USER_DATA_ROOT");
            layout = LauncherInstallationLayout.CreateDefault(
                installRoot,
                userDataRoot: verificationUserDataRoot);
            singleInstance = LauncherSingleInstanceGuard.Acquire("ChatbotLauncher.Trial");
            var config = LauncherConfig.LoadFromFile(Path.Combine(installRoot, "launcher.json"));
            var vcRuntime = VcRuntimeLaunchPolicy.CreateDefault(new DefaultLauncherFileSystem(), new DefaultLauncherClock())
                .EnsureAvailable(layout);
            if (vcRuntime.Status != VcRuntimeCheckStatus.Ready)
            {
                throw new LauncherUserFacingException(
                    vcRuntime.Message,
                    LauncherExitCodes.ConfigurationOrBundleError,
                    vcRuntime.Status.ToString().ToUpperInvariant());
            }
            var manager = LauncherProcessManager.CreateDefault(config, layout);
            manager.StartAsync().GetAwaiter().GetResult();
            var trayController = new TrayController(manager);
            Application.Run(new LauncherApplicationContext(manager, trayController));
            return 0;
        }
        catch (Exception ex)
        {
            return LauncherFailurePresenter.Present(
                ex,
                LauncherEnvironment.IsNonInteractive(),
                layout,
                Console.Error,
                new MessageBoxLauncherUiNotifier()).ExitCode;
        }
        finally
        {
            singleInstance?.Dispose();
        }
    }
}

public static class LauncherContracts
{
    public const int SchemaVersion = 1;
    public const string DefaultBackendHost = "127.0.0.1";
    public const int DefaultBackendPort = 5302;
    public const string DefaultHealthPath = "/healthz";
    public const string DefaultRuntimeStatusPath = "/api/v1/desktop-automation/runtime/status";
    public const int DefaultStartupTimeoutSeconds = 60;
    public const string DefaultStateRelativePath = @"runtime\launcher-state.json";
}

public sealed record LauncherConfig(
    [property: JsonPropertyName("schemaVersion")] int SchemaVersion,
    [property: JsonPropertyName("backend")] LauncherBackendConfig Backend)
{
    public static LauncherConfig LoadFromFile(string path)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        return Parse(File.ReadAllText(path));
    }

    public static LauncherConfig Parse(string json)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(json);
        var config = JsonSerializer.Deserialize(json, LauncherJsonContext.Default.LauncherConfig)
            ?? throw new InvalidOperationException("launcher.json did not contain a launcher config object.");
        config.Validate();
        return config;
    }

    public void Validate()
    {
        if (SchemaVersion != LauncherContracts.SchemaVersion)
        {
            throw new InvalidOperationException(
                $"launcher schemaVersion must be {LauncherContracts.SchemaVersion}, got {SchemaVersion}.");
        }

        Backend.Validate();
    }
}

public sealed record LauncherBackendConfig(
    [property: JsonPropertyName("host")] string Host,
    [property: JsonPropertyName("port")] int Port,
    [property: JsonPropertyName("healthPath")] string HealthPath,
    [property: JsonPropertyName("runtimeStatusPath")] string RuntimeStatusPath,
    [property: JsonPropertyName("startupTimeoutSeconds")] int StartupTimeoutSeconds)
{
    public Uri BackendBaseUri => new($"http://{Host}:{Port}/", UriKind.Absolute);

    public Uri HealthUri => new(BackendBaseUri, NormalizePath(HealthPath));

    public Uri RuntimeStatusUri => new(BackendBaseUri, NormalizePath(RuntimeStatusPath));

    public void Validate()
    {
        if (!string.Equals(Host, LauncherContracts.DefaultBackendHost, StringComparison.Ordinal))
        {
            throw new InvalidOperationException("launcher backend host must stay fixed at 127.0.0.1 in packaged mode.");
        }

        if (Port is < 1 or > 65535)
        {
            throw new InvalidOperationException($"launcher backend port must be between 1 and 65535, got {Port}.");
        }

        if (!IsAbsoluteAppPath(HealthPath))
        {
            throw new InvalidOperationException("launcher healthPath must start with '/'.");
        }

        if (!IsAbsoluteAppPath(RuntimeStatusPath))
        {
            throw new InvalidOperationException("launcher runtimeStatusPath must start with '/'.");
        }

        if (StartupTimeoutSeconds is < 5 or > 600)
        {
            throw new InvalidOperationException(
                $"launcher startupTimeoutSeconds must be between 5 and 600, got {StartupTimeoutSeconds}.");
        }
    }

    private static bool IsAbsoluteAppPath(string path)
    {
        return !string.IsNullOrWhiteSpace(path)
            && path.StartsWith("/", StringComparison.Ordinal)
            && !path.StartsWith("//", StringComparison.Ordinal);
    }

    private static string NormalizePath(string path)
    {
        return path.StartsWith("/", StringComparison.Ordinal) ? path[1..] : path;
    }
}

public sealed record LauncherState(
    [property: JsonPropertyName("schemaVersion")] int SchemaVersion,
    [property: JsonPropertyName("lastUpdatedUtc")] DateTimeOffset LastUpdatedUtc,
    [property: JsonPropertyName("backend")] LauncherOwnedBackendState? Backend,
    [property: JsonPropertyName("lastKnownUrls")] LauncherStateUrls LastKnownUrls,
    [property: JsonPropertyName("safety")] LauncherStateSafety Safety);

public sealed record LauncherOwnedBackendState(
    [property: JsonPropertyName("pid")] int Pid,
    [property: JsonPropertyName("processCreateTimeUtc")] string ProcessCreateTimeUtc,
    [property: JsonPropertyName("executablePath")] string ExecutablePath,
    [property: JsonPropertyName("sessionId")] string SessionId);

public sealed record LauncherStateUrls(
    [property: JsonPropertyName("backendBaseUrl")] string BackendBaseUrl,
    [property: JsonPropertyName("healthUrl")] string HealthUrl,
    [property: JsonPropertyName("runtimeStatusUrl")] string RuntimeStatusUrl);

public sealed record LauncherStateSafety(
    [property: JsonPropertyName("broadcastSendEnabled")] bool BroadcastSendEnabled,
    [property: JsonPropertyName("rpaAutoSendEnabled")] bool RpaAutoSendEnabled);

public sealed record LauncherDiagnosticsDefinition(
    [property: JsonPropertyName("schemaVersion")] int SchemaVersion,
    [property: JsonPropertyName("bundleEntries")] IReadOnlyList<LauncherDiagnosticsBundleEntry> BundleEntries,
    [property: JsonPropertyName("redactionRules")] IReadOnlyList<string> RedactionRules,
    [property: JsonPropertyName("legacyDirectoryChecks")] IReadOnlyList<LauncherLegacyDirectoryCheck> LegacyDirectoryChecks);

public sealed record LauncherDiagnosticsBundleEntry(
    [property: JsonPropertyName("relativePath")] string RelativePath,
    [property: JsonPropertyName("required")] bool Required,
    [property: JsonPropertyName("description")] string Description);

public sealed record LauncherLegacyDirectoryCheck(
    [property: JsonPropertyName("logicalName")] string LogicalName,
    [property: JsonPropertyName("pathPattern")] string PathPattern,
    [property: JsonPropertyName("note")] string Note);

public sealed record LauncherDiagnosticsContext(string? InstallRoot, string? UserDataRoot);

public sealed record LauncherRedactionResult(string RedactedText, IReadOnlyList<string> AppliedRules);

public static class LauncherDiagnostics
{
    private static readonly Regex JsonSecretPattern = new(
        "(?<prefix>\"(?:token|cookie|password|secret|authorization)\"\\s*:\\s*\")(?<value>.*?)(?<suffix>\")",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex AssignmentSecretPattern = new(
        "(?<prefix>\\b(?:token|cookie|password|secret|authorization)\\b\\s*[:=]\\s*)(?<value>[^\\r\\n;]+)",
        RegexOptions.IgnoreCase | RegexOptions.Compiled);

    private static readonly Regex WindowsPathPattern = new(
        @"(?<![A-Za-z0-9_])(?:[A-Za-z]:\\[^\\/:*?""<>|\r\n]+(?:\\[^\\/:*?""<>|\r\n]+)*|\\\\[^\\/:*?""<>|\r\n]+\\[^\\/:*?""<>|\r\n]+(?:\\[^\\/:*?""<>|\r\n]+)*)",
        RegexOptions.Compiled);

    public static LauncherDiagnosticsDefinition BuildDefinition()
    {
        return new LauncherDiagnosticsDefinition(
            LauncherContracts.SchemaVersion,
            new[]
            {
                new LauncherDiagnosticsBundleEntry("launcher.json", true, "Launcher packaged configuration."),
                new LauncherDiagnosticsBundleEntry("logs/launcher.log", false, "Launcher runtime log with redaction."),
                new LauncherDiagnosticsBundleEntry("logs/backend.log", false, "Packaged backend log with redaction."),
                new LauncherDiagnosticsBundleEntry("runtime/launcher-state.json", false, "Launcher-owned backend identity snapshot."),
                new LauncherDiagnosticsBundleEntry("manifest.json", false, "Release manifest used for key-file verification."),
                new LauncherDiagnosticsBundleEntry("build-report.json", false, "Release build metadata for maintainer diagnostics."),
            },
            new[]
            {
                "Redact secret-bearing values for token, cookie, password, secret, and Authorization fields.",
                "Replace absolute install-root and user-data paths with stable placeholders before export.",
                "Replace other absolute Windows paths with <ABSOLUTE_PATH> to avoid developer-machine leakage.",
            },
            new[]
            {
                new LauncherLegacyDirectoryCheck(
                    "legacy-wecomebot-user-data",
                    @"%LOCALAPPDATA%\WecomeBot",
                    "Legacy WecomeBot directories may be noted in diagnostics but must never be auto-migrated."),
            });
    }

    public static LauncherRedactionResult RedactText(string rawText, LauncherDiagnosticsContext context)
    {
        ArgumentNullException.ThrowIfNull(rawText);
        ArgumentNullException.ThrowIfNull(context);

        var appliedRules = new List<string>();
        var redacted = JsonSecretPattern.Replace(rawText, static match =>
        {
            return $"{match.Groups["prefix"].Value}[REDACTED]{match.Groups["suffix"].Value}";
        });
        if (!ReferenceEquals(redacted, rawText) && !appliedRules.Contains("json-secret-values"))
        {
            appliedRules.Add("json-secret-values");
        }

        var assignmentRedacted = AssignmentSecretPattern.Replace(redacted, static match =>
        {
            return $"{match.Groups["prefix"].Value}[REDACTED]";
        });
        if (!ReferenceEquals(assignmentRedacted, redacted) && !appliedRules.Contains("assignment-secret-values"))
        {
            appliedRules.Add("assignment-secret-values");
        }

        redacted = assignmentRedacted;

        var replacements = BuildRootReplacements(context);
        redacted = WindowsPathPattern.Replace(redacted, match =>
        {
            foreach (var replacement in replacements)
            {
                if (match.Value.StartsWith(replacement.Root, StringComparison.OrdinalIgnoreCase))
                {
                    if (!appliedRules.Contains(replacement.RuleName))
                    {
                        appliedRules.Add(replacement.RuleName);
                    }

                    var suffix = match.Value[replacement.Root.Length..].TrimStart('\\');
                    return string.IsNullOrEmpty(suffix)
                        ? replacement.Placeholder
                        : $"{replacement.Placeholder}\\{suffix}";
                }
            }

            if (!appliedRules.Contains("absolute-paths"))
            {
                appliedRules.Add("absolute-paths");
            }

            return "<ABSOLUTE_PATH>";
        });

        return new LauncherRedactionResult(redacted, appliedRules);
    }

    private static IReadOnlyList<(string Root, string Placeholder, string RuleName)> BuildRootReplacements(
        LauncherDiagnosticsContext context)
    {
        var replacements = new List<(string Root, string Placeholder, string RuleName)>();
        AddReplacement(replacements, context.InstallRoot, "%INSTALL_ROOT%", "install-root-paths");
        AddReplacement(replacements, context.UserDataRoot, "%USER_DATA_ROOT%", "user-data-root-paths");
        return replacements
            .OrderByDescending(item => item.Root.Length)
            .ToArray();
    }

    private static void AddReplacement(
        ICollection<(string Root, string Placeholder, string RuleName)> replacements,
        string? root,
        string placeholder,
        string ruleName)
    {
        if (string.IsNullOrWhiteSpace(root))
        {
            return;
        }

        replacements.Add((Path.GetFullPath(root).TrimEnd('\\'), placeholder, ruleName));
    }
}

[JsonSerializable(typeof(LauncherConfig))]
internal partial class LauncherJsonContext : JsonSerializerContext;

public static class LauncherEnvironment
{
    public const string NonInteractiveVariable = "CHATBOT_LAUNCHER_NONINTERACTIVE";

    public static bool IsNonInteractive()
    {
        return string.Equals(
            Environment.GetEnvironmentVariable(NonInteractiveVariable),
            "1",
            StringComparison.Ordinal);
    }
}

public sealed class LauncherSingleInstanceGuard : IDisposable
{
    private readonly Mutex _mutex;

    private LauncherSingleInstanceGuard(Mutex mutex)
    {
        _mutex = mutex;
    }

    public static LauncherSingleInstanceGuard Acquire(string name)
    {
        var mutex = new Mutex(initiallyOwned: true, $@"Local\{name}", out var createdNew);
        if (!createdNew)
        {
            mutex.Dispose();
            throw new LauncherUserFacingException(
                LauncherText.AlreadyRunning(),
                LauncherExitCodes.AlreadyRunning,
                "LAUNCHER_ALREADY_RUNNING");
        }

        return new LauncherSingleInstanceGuard(mutex);
    }

    public void Dispose()
    {
        _mutex.ReleaseMutex();
        _mutex.Dispose();
    }
}

public interface ILauncherUiNotifier
{
    void ShowError(string message);
}

internal sealed class MessageBoxLauncherUiNotifier : ILauncherUiNotifier
{
    public void ShowError(string message)
    {
        MessageBox.Show(
            message,
            LauncherText.ErrorTitle(),
            MessageBoxButtons.OK,
            MessageBoxIcon.Error);
    }
}

public sealed record LauncherFailureResult(int ExitCode, string Message);

public static class LauncherFailurePresenter
{
    public static LauncherFailureResult Present(
        Exception exception,
        bool nonInteractive,
        LauncherInstallationLayout? layout,
        TextWriter errorWriter,
        ILauncherUiNotifier notifier)
    {
        ArgumentNullException.ThrowIfNull(exception);
        ArgumentNullException.ThrowIfNull(errorWriter);
        ArgumentNullException.ThrowIfNull(notifier);

        var failure = exception as LauncherUserFacingException
            ?? new LauncherUserFacingException(
                LauncherText.ConfigurationOrBundleError(exception.Message),
                LauncherExitCodes.ConfigurationOrBundleError,
                "CONFIGURATION_OR_BUNDLE_ERROR",
                exception);
        TryWriteFailureLog(layout, failure);
        if (nonInteractive)
        {
            errorWriter.WriteLine($"[{failure.DiagnosticCode}] {failure.Message}");
        }
        else
        {
            notifier.ShowError(failure.Message);
        }

        return new LauncherFailureResult(failure.ExitCode, failure.Message);
    }

    private static void TryWriteFailureLog(LauncherInstallationLayout? layout, LauncherUserFacingException failure)
    {
        try
        {
            if (layout is null)
            {
                return;
            }

            Directory.CreateDirectory(layout.LogRoot);
            var logPath = Path.Combine(layout.LogRoot, "launcher.log");
            File.AppendAllText(
                logPath,
                $"{DateTimeOffset.UtcNow:O} [{failure.DiagnosticCode}] {failure.Message}{Environment.NewLine}",
                System.Text.Encoding.UTF8);
        }
        catch
        {
        }
    }
}

public static class LauncherText
{
    private static bool IsChinese =>
        string.Equals(CultureInfo.CurrentUICulture.TwoLetterISOLanguageName, "zh", StringComparison.OrdinalIgnoreCase);

    public static string ErrorTitle() => IsChinese ? "Chatbot 启动器" : "Chatbot Launcher";

    public static string AlreadyRunning() =>
        IsChinese ? "Chatbot 已在运行。请先关闭现有启动器实例。" : "Chatbot is already running.";

    public static string ReadyStatus(bool sendEnabled) =>
        IsChinese
            ? $"后端已就绪；桌面运行时可用；真实发送{(sendEnabled ? "已启用" : "默认禁用")}。"
            : $"Backend ready; desktop runtime reachable; real send {(sendEnabled ? "enabled" : "disabled by default")}.";

    public static string PendingStatus(string status) =>
        IsChinese ? $"桌面运行时状态：{status}" : $"Desktop runtime status: {status}";

    public static string PortConflict(int port, int? owningPid = null, string? owningExecutablePath = null)
    {
        var owner = owningPid is null
            ? string.Empty
            : IsChinese
                ? $"{Environment.NewLine}占用进程 PID：{owningPid}; 路径：{owningExecutablePath}"
                : $"{Environment.NewLine}Owning PID: {owningPid}; path: {owningExecutablePath}";
        return IsChinese
            ? $"端口 {port} 已被其他进程占用。请关闭冲突进程或修改 launcher.json。{owner}"
            : $"Port {port} is already owned by another process. Close the conflicting process or update launcher.json.{owner}";
    }

    public static string BackendStartFailed(LauncherStartupFailureDetails details) =>
        (IsChinese ? "打包后端进程启动失败。" : "Packaged backend process failed to start.")
        + Environment.NewLine + Environment.NewLine
        + FormatStartupFailureDetails(details);

    public static string BackendExitedEarly(LauncherStartupFailureDetails details) =>
        (IsChinese ? "打包后端在健康检查就绪前提前退出。" : "Packaged backend exited before health became ready.")
        + Environment.NewLine + Environment.NewLine
        + FormatStartupFailureDetails(details);

    public static string BackendHealthTimeout(int timeoutSeconds, LauncherStartupFailureDetails details) =>
        (IsChinese
            ? $"打包后端在 {timeoutSeconds} 秒内未通过健康检查。"
            : $"Packaged backend did not become healthy within {timeoutSeconds} seconds.")
        + Environment.NewLine + Environment.NewLine
        + FormatStartupFailureDetails(details);

    public static string ConfigurationOrBundleError(string message) =>
        IsChinese
            ? $"启动器配置或发行文件无效：{message}"
            : $"Launcher configuration or bundle is invalid: {message}";

    public static string DiagnosticsExported(string path) =>
        IsChinese ? $"诊断包已导出：{path}" : $"Diagnostics exported: {path}";

    public static string VcRuntimeMissingForInstalledFlow() =>
        IsChinese
            ? "检测到缺少 VC++ 2015-2022 x64 运行库。常规安装场景应由安装程序负责安装该前置条件，请重新运行 Setup。"
            : "VC++ 2015-2022 x64 runtime is missing. For normal installed deployments, rerun Setup so it can install the prerequisite.";

    public static string VcRuntimeInstallerMissing() =>
        IsChinese
            ? "便携版缺少 prerequisites\\vc_redist.x64.exe，无法执行一次性前置安装。"
            : "Portable fallback cannot continue because prerequisites\\vc_redist.x64.exe is missing.";

    public static string VcRuntimePortablePrompt() =>
        IsChinese
            ? "检测到缺少 VC++ 运行库。是否立即以管理员权限安装 prerequisites\\vc_redist.x64.exe？此入口仅用于便携版的一次性恢复。"
            : "The VC++ runtime is missing. Install prerequisites\\vc_redist.x64.exe now with elevation? This launcher entrypoint is only a one-time Portable fallback.";

    public static string VcRuntimePortableDeclined() =>
        IsChinese
            ? "你已取消本次便携版 VC++ 前置安装请求。启动器不会在每次启动时重复请求提升权限。"
            : "You declined the Portable VC++ prerequisite flow. The launcher will not request elevation again on every startup.";

    public static string VcRuntimeInstalled() =>
        IsChinese ? "VC++ 运行库安装成功。" : "VC++ runtime installed successfully.";

    public static string VcRuntimeUacCancelled() =>
        IsChinese
            ? "已取消 VC++ 运行库安装的 UAC 提升请求。"
            : "VC++ runtime installation was cancelled at the UAC prompt.";

    public static string VcRuntimeInstallFailed(int exitCode) =>
        IsChinese
            ? $"VC++ 运行库安装失败，退出码 {exitCode}。"
            : $"VC++ runtime installation failed with exit code {exitCode}.";

    public static string VcRuntimeRetryBlocked(VcRuntimeCheckStatus previousStatus) =>
        IsChinese
            ? $"之前的便携版 VC++ 前置安装尝试状态为 {previousStatus}。启动器不会在每次启动时重复请求提升权限，请手动修复后重试。"
            : $"A previous Portable VC++ prerequisite attempt ended with {previousStatus}. The launcher will not request elevation again on every startup.";

    private static string FormatStartupFailureDetails(LauncherStartupFailureDetails details)
    {
        return string.Join(
            Environment.NewLine,
            new[]
            {
                $"BackendPid: {details.BackendPid?.ToString(CultureInfo.InvariantCulture) ?? "unknown"}",
                $"ExitCode: {details.ExitCode?.ToString(CultureInfo.InvariantCulture) ?? "unknown"}",
                $"ExecutablePath: {details.ExecutablePath}",
                $"CommandLine: {details.CommandLine}",
                $"stdout: {details.StandardOutputPath}",
                $"stderr: {details.StandardErrorPath}",
                $"Summary: {details.LastErrorSummary}",
            });
    }
}
