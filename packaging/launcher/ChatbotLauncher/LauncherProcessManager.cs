using System.Diagnostics;
using System.Globalization;
using System.IO.Compression;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace ChatbotLauncher;

public sealed record LauncherInstallationLayout(
    string InstallRoot,
    string UserDataRoot,
    string DataRoot,
    string RuntimeRoot,
    string LogRoot,
    string ResourcesRoot,
    string ResourcesWebRoot,
    string BackendPythonExecutable,
    string BackendEntrypointPath,
    string ConnectorPythonExecutable,
    string ConnectorRuntimeScriptPath,
    string RpaRuntimeExecutable,
    string ShutdownRequestPath)
{
    public static LauncherInstallationLayout CreateDefault(
        string installRoot,
        string? localAppData = null,
        string? userDataRoot = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(installRoot);

        var resolvedInstallRoot = Path.GetFullPath(installRoot);
        var resolvedLocalAppData = string.IsNullOrWhiteSpace(localAppData)
            ? Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
            : localAppData;
        if (string.IsNullOrWhiteSpace(resolvedLocalAppData))
        {
            throw new LauncherUserFacingException("LOCALAPPDATA is unavailable for the packaged launcher.");
        }

        var resolvedUserDataRoot = string.IsNullOrWhiteSpace(userDataRoot)
            ? Path.Combine(resolvedLocalAppData, "Chatbot")
            : Path.GetFullPath(userDataRoot);
        var runtimeRoot = Path.Combine(resolvedUserDataRoot, "runtime");
        var logRoot = Path.Combine(resolvedUserDataRoot, "logs");
        var dataRoot = Path.Combine(resolvedUserDataRoot, "data");
        var resourcesRoot = Path.Combine(resolvedInstallRoot, "resources");

        return new LauncherInstallationLayout(
            InstallRoot: resolvedInstallRoot,
            UserDataRoot: resolvedUserDataRoot,
            DataRoot: dataRoot,
            RuntimeRoot: runtimeRoot,
            LogRoot: logRoot,
            ResourcesRoot: resourcesRoot,
            ResourcesWebRoot: Path.Combine(resourcesRoot, "web", "dist"),
            BackendPythonExecutable: Path.Combine(resolvedInstallRoot, "server", "runtime", "python", "python.exe"),
            BackendEntrypointPath: Path.Combine(resolvedInstallRoot, "server", "app", "packaging", "server", "entrypoint.py"),
            ConnectorPythonExecutable: Path.Combine(resolvedInstallRoot, "connectors", "runtime", "python", "python.exe"),
            ConnectorRuntimeScriptPath: Path.Combine(
                resolvedInstallRoot,
                "connectors",
                "app",
                "wechat-decrypt",
                "connector_runtime.py"),
            RpaRuntimeExecutable: Path.Combine(
                resolvedInstallRoot,
                "runtime",
                "desktop-rpa",
                "LangBot Desktop RPA Runtime.exe"),
            ShutdownRequestPath: Path.Combine(runtimeRoot, "backend-shutdown.json"));
    }

    public IReadOnlyList<LauncherRequiredArtifact> GetRequiredArtifacts()
    {
        return new[]
        {
            new LauncherRequiredArtifact(BackendPythonExecutable, false, "backend runtime python"),
            new LauncherRequiredArtifact(BackendEntrypointPath, false, "backend packaged entrypoint"),
            new LauncherRequiredArtifact(ConnectorPythonExecutable, false, "connector runtime python"),
            new LauncherRequiredArtifact(ConnectorRuntimeScriptPath, false, "connector runtime script"),
            new LauncherRequiredArtifact(ResourcesRoot, true, "shared resources root"),
            new LauncherRequiredArtifact(ResourcesWebRoot, true, "packaged web dist"),
            new LauncherRequiredArtifact(RpaRuntimeExecutable, false, "Desktop RPA runtime executable"),
        };
    }
}

public sealed record LauncherRequiredArtifact(string Path, bool Directory, string Description);

public sealed record LauncherLaunchRequest(
    string ExecutablePath,
    string WorkingDirectory,
    IReadOnlyList<string> Arguments,
    IReadOnlyDictionary<string, string> Environment,
    string CommandLine,
    string StandardOutputPath,
    string StandardErrorPath);

public sealed record LauncherProcessSnapshot(int Pid, string ExecutablePath, DateTimeOffset CreateTimeUtc);

public sealed record LauncherRuntimeObservation(string Status, bool RuntimeReachable, bool SendEnabled)
{
    public bool IsReady =>
        RuntimeReachable || string.Equals(Status, "ready", StringComparison.OrdinalIgnoreCase);
}

public sealed record LauncherStartupFailureDetails(
    int? BackendPid,
    int? ExitCode,
    string ExecutablePath,
    string CommandLine,
    string StandardOutputPath,
    string StandardErrorPath,
    string LastErrorSummary);

public interface ILauncherProcess : IDisposable
{
    bool HasExited { get; }

    int? ExitCode { get; }

    LauncherProcessSnapshot GetSnapshot();

    Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken);

    void KillTree();
}

public sealed record LauncherPortOwnershipReport(
    bool IsListening,
    bool OwnedByCurrentProcess,
    bool OwnedByOtherProcess,
    int? OwningPid,
    string OwningExecutablePath);

public interface ILauncherProcessLauncher
{
    ILauncherProcess Start(LauncherLaunchRequest request);
}

public interface ILauncherPortOwnershipProbe
{
    LauncherPortOwnershipReport Inspect(int port, LauncherProcessSnapshot ownedSnapshot);
}

public interface ILauncherHttpProbeClient
{
    Task<bool> CheckHealthAsync(Uri uri, CancellationToken cancellationToken);

    Task<LauncherRuntimeObservation> GetRuntimeStatusAsync(Uri uri, CancellationToken cancellationToken);
}

public interface ILauncherBrowserLauncher
{
    void Open(Uri uri);
}

public interface ILauncherFileSystem
{
    bool FileExists(string path);

    bool DirectoryExists(string path);

    void CreateDirectory(string path);

    void DeleteFile(string path);

    void WriteAllText(string path, string contents);

    string ReadAllText(string path);

    byte[] ReadAllBytes(string path);

    long GetFileSize(string path);
}

public interface ILauncherClock
{
    DateTimeOffset UtcNow { get; }

    Task Delay(TimeSpan delay, CancellationToken cancellationToken);
}

public sealed class LauncherUserFacingException : Exception
{
    public LauncherUserFacingException(
        string message,
        int exitCode = LauncherExitCodes.ConfigurationOrBundleError,
        string diagnosticCode = "LAUNCHER_FAILURE",
        Exception? innerException = null)
        : base(message, innerException)
    {
        ExitCode = exitCode;
        DiagnosticCode = diagnosticCode;
    }

    public int ExitCode { get; }

    public string DiagnosticCode { get; }
}

public static class LauncherExitCodes
{
    public const int PortOwnedByOtherProcess = 20;
    public const int BackendStartFailed = 21;
    public const int BackendExitedEarly = 22;
    public const int BackendHealthTimeout = 23;
    public const int ConfigurationOrBundleError = 24;
    public const int AlreadyRunning = 25;
}

public sealed class LauncherProcessManager
{
    private static readonly TimeSpan PollInterval = TimeSpan.FromMilliseconds(250);
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
    };

    private readonly LauncherConfig _config;
    private readonly LauncherInstallationLayout _layout;
    private readonly ILauncherProcessLauncher _processLauncher;
    private readonly ILauncherHttpProbeClient _httpProbeClient;
    private readonly ILauncherBrowserLauncher _browserLauncher;
    private readonly ILauncherPortOwnershipProbe _portOwnershipProbe;
    private readonly ILauncherFileSystem _fileSystem;
    private readonly ILauncherClock _clock;
    private readonly object _sync = new();

    private ILauncherProcess? _ownedProcess;
    private LauncherProcessSnapshot? _ownedSnapshot;
    private LauncherLaunchRequest? _ownedLaunchRequest;
    private LauncherRuntimeObservation? _lastObservation;

    public LauncherProcessManager(
        LauncherConfig config,
        LauncherInstallationLayout layout,
        ILauncherProcessLauncher processLauncher,
        ILauncherHttpProbeClient httpProbeClient,
        ILauncherBrowserLauncher browserLauncher,
        ILauncherPortOwnershipProbe portOwnershipProbe,
        ILauncherFileSystem fileSystem,
        ILauncherClock clock)
    {
        _config = config;
        _layout = layout;
        _processLauncher = processLauncher;
        _httpProbeClient = httpProbeClient;
        _browserLauncher = browserLauncher;
        _portOwnershipProbe = portOwnershipProbe;
        _fileSystem = fileSystem;
        _clock = clock;
    }

    public Uri BrowserUri => _config.Backend.BackendBaseUri;

    public LauncherRuntimeObservation? LastObservation => _lastObservation;

    public static LauncherProcessManager CreateDefault(LauncherConfig config, LauncherInstallationLayout layout)
    {
        return new LauncherProcessManager(
            config,
            layout,
            new DefaultLauncherProcessLauncher(),
            new DefaultLauncherHttpProbeClient(),
            new DefaultLauncherBrowserLauncher(),
            new DefaultLauncherPortOwnershipProbe(),
            new DefaultLauncherFileSystem(),
            new DefaultLauncherClock());
    }

    public static string QuoteCommandLineArgument(string? value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return "\"\"";
        }

        if (!value.Any(static ch => char.IsWhiteSpace(ch) || ch == '"'))
        {
            return value;
        }

        var escaped = Regex.Replace(
            value,
            "(\\\\*)\"",
            static match => match.Groups[1].Value + match.Groups[1].Value + "\\\"");
        escaped = Regex.Replace(
            escaped,
            "(\\\\+)$",
            static match => match.Groups[1].Value + match.Groups[1].Value);
        return $"\"{escaped}\"";
    }

    public static string BuildCommandLineArguments(IEnumerable<string?> arguments)
    {
        ArgumentNullException.ThrowIfNull(arguments);
        return string.Join(" ", arguments.Select(QuoteCommandLineArgument));
    }

    public IReadOnlyDictionary<string, string> BuildPackagedEnvironment()
    {
        return new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["CHATBOT_PACKAGED"] = "1",
            ["CHATBOT_INSTALL_ROOT"] = _layout.InstallRoot,
            ["CHATBOT_USER_DATA_ROOT"] = _layout.UserDataRoot,
            ["LANGBOT_DATA_ROOT"] = _layout.DataRoot,
            ["CHATBOT_RESOURCES_ROOT"] = _layout.ResourcesRoot,
            ["CHATBOT_WEB_ROOT"] = _layout.ResourcesWebRoot,
            ["CHATBOT_TEMPLATE_ROOT"] = Path.Combine(_layout.ResourcesRoot, "templates"),
            ["CHATBOT_MIGRATION_ROOT"] = Path.Combine(_layout.ResourcesRoot, "migrations"),
            ["CHATBOT_DEFAULTS_ROOT"] = Path.Combine(_layout.ResourcesRoot, "defaults"),
            ["CHATBOT_LOG_ROOT"] = _layout.LogRoot,
            ["CHATBOT_RUNTIME_ROOT"] = _layout.RuntimeRoot,
            ["CHATBOT_RPA_RUNTIME_PATH"] = _layout.RpaRuntimeExecutable,
            ["CHATBOT_BACKEND_HEALTH_PATH"] = _config.Backend.HealthPath,
            ["CHATBOT_BACKEND_RUNTIME_STATUS_PATH"] = _config.Backend.RuntimeStatusPath,
            ["API__HOST"] = _config.Backend.Host,
            ["API__PORT"] = _config.Backend.Port.ToString(CultureInfo.InvariantCulture),
            ["DESKTOP_AUTOMATION__ENABLED"] = "true",
            ["DESKTOP_AUTOMATION__RUNTIME_EXECUTABLE"] = _layout.RpaRuntimeExecutable,
            ["PYTHONDONTWRITEBYTECODE"] = "1",
            ["PYTHONUTF8"] = "1",
            ["PYTHONIOENCODING"] = "utf-8",
            ["LANGBOT_BROADCAST_SEND_ENABLED"] = "0",
            ["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"] = string.Empty,
            ["LANGBOT_RPA_ALLOW_AUTO_SEND"] = "0",
            ["LANGBOT_RPA_FORCE_DISABLE_SEND"] = "1",
        };
    }

    public void ValidateInstallation()
    {
        foreach (var artifact in _layout.GetRequiredArtifacts())
        {
            var exists = artifact.Directory
                ? _fileSystem.DirectoryExists(artifact.Path)
                : _fileSystem.FileExists(artifact.Path);
            if (!exists)
            {
                throw new LauncherUserFacingException(
                    $"Packaged installation is incomplete: missing {artifact.Description} ({artifact.Path}).");
            }
        }

        new ManifestValidator(_fileSystem).Validate(_layout.InstallRoot);
    }

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        EnsureWorkingDirectories();
        ValidateInstallation();

        lock (_sync)
        {
            if (_ownedProcess is not null)
            {
                return;
            }
        }

        ThrowIfConfiguredPortOwnedByOtherProcess();

        var request = BuildLaunchRequest();
        AppendLauncherLog($"Starting packaged backend: {request.CommandLine}");
        ILauncherProcess process;
        try
        {
            process = _processLauncher.Start(request);
        }
        catch (LauncherUserFacingException)
        {
            throw;
        }
        catch (Exception ex)
        {
            var startFailure = CreateBackendStartFailure(request, ex);
            AppendLauncherLog(startFailure.Message);
            throw startFailure;
        }

        var snapshot = process.GetSnapshot();

        lock (_sync)
        {
            _ownedProcess = process;
            _ownedSnapshot = snapshot;
            _ownedLaunchRequest = request;
            _lastObservation = null;
        }

        try
        {
            await WaitForHealthAsync(process, cancellationToken).ConfigureAwait(false);
            await WaitForRuntimeReadyAsync(cancellationToken).ConfigureAwait(false);
            PersistLauncherState(snapshot);
            _browserLauncher.Open(BrowserUri);
        }
        catch
        {
            await StopAsync("startup-failed", cancellationToken).ConfigureAwait(false);
            throw;
        }
    }

    public async Task RestartAsync(CancellationToken cancellationToken = default)
    {
        await StopAsync("restart", cancellationToken).ConfigureAwait(false);
        await StartAsync(cancellationToken).ConfigureAwait(false);
    }

    public async Task StopAsync(string reason = "launcher-exit", CancellationToken cancellationToken = default)
    {
        ILauncherProcess? process;
        LauncherProcessSnapshot? snapshot;
        lock (_sync)
        {
            process = _ownedProcess;
            snapshot = _ownedSnapshot;
        }

        if (process is null || snapshot is null)
        {
            PersistLauncherState(null);
            return;
        }

        WriteShutdownRequest(reason);
        if (!await process.WaitForExitAsync(TimeSpan.FromSeconds(10), cancellationToken).ConfigureAwait(false))
        {
            if (IsOwnedProcess(process, snapshot))
            {
                AppendLauncherLog($"Force killing owned backend process tree: pid={snapshot.Pid}");
                process.KillTree();
                await process.WaitForExitAsync(TimeSpan.FromSeconds(5), cancellationToken).ConfigureAwait(false);
            }
            else
            {
                AppendLauncherLog($"Refused force kill because ownership changed: pid={snapshot.Pid}");
            }
        }

        process.Dispose();
        lock (_sync)
        {
            _ownedProcess = null;
            _ownedSnapshot = null;
            _ownedLaunchRequest = null;
            _lastObservation = null;
        }

        PersistLauncherState(null);
    }

    public async Task<string> GetStatusSummaryAsync(CancellationToken cancellationToken = default)
    {
        var observation = _lastObservation ?? await ObserveRuntimeStatusAsync(cancellationToken).ConfigureAwait(false);
        return observation.IsReady
            ? LauncherText.ReadyStatus(observation.SendEnabled)
            : LauncherText.PendingStatus(observation.Status);
    }

    public void OpenBrowser()
    {
        _browserLauncher.Open(BrowserUri);
    }

    public async Task<string> ExportDiagnosticsAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        var diagnosticsRoot = Path.Combine(_layout.RuntimeRoot, "diagnostics");
        Directory.CreateDirectory(diagnosticsRoot);
        var fileName = $"ChatbotLauncher-diagnostics-{_clock.UtcNow:yyyyMMdd-HHmmss}.zip";
        var zipPath = Path.Combine(diagnosticsRoot, fileName);

        var definition = LauncherDiagnostics.BuildDefinition();
        var legacyChecks = definition.LegacyDirectoryChecks
            .Select(check => new
            {
                check.LogicalName,
                check.PathPattern,
                Exists = ResolveLegacyPathExists(check.PathPattern),
                check.Note,
            })
            .ToArray();

        var reportJson = JsonSerializer.Serialize(
            new
            {
                schemaVersion = definition.SchemaVersion,
                generatedAtUtc = _clock.UtcNow,
                backend = new
                {
                    host = _config.Backend.Host,
                    port = _config.Backend.Port,
                    healthPath = _config.Backend.HealthPath,
                    runtimeStatusPath = _config.Backend.RuntimeStatusPath,
                },
                bundleEntries = definition.BundleEntries,
                redactionRules = definition.RedactionRules,
                legacyDirectoryChecks = legacyChecks,
                lastObservation = _lastObservation,
                statePath = Path.Combine(_layout.RuntimeRoot, "launcher-state.json"),
            },
            JsonOptions);

        var redactedReport = LauncherDiagnostics.RedactText(
            reportJson,
            new LauncherDiagnosticsContext(_layout.InstallRoot, _layout.UserDataRoot));

        using (var stream = File.Create(zipPath))
        using (var archive = new ZipArchive(stream, ZipArchiveMode.Create))
        {
            WriteArchiveEntry(archive, "report.json", redactedReport.RedactedText);

            var statePath = Path.Combine(_layout.RuntimeRoot, "launcher-state.json");
            if (_fileSystem.FileExists(statePath))
            {
                WriteArchiveEntry(
                    archive,
                    "launcher-state.json",
                    LauncherDiagnostics.RedactText(
                        _fileSystem.ReadAllText(statePath),
                        new LauncherDiagnosticsContext(_layout.InstallRoot, _layout.UserDataRoot)).RedactedText);
            }

            WriteArchiveEntry(archive, "launcher.json", _fileSystem.ReadAllText(Path.Combine(_layout.InstallRoot, "launcher.json")));
        }

        return zipPath;
    }

    public bool IsOwnedProcess(ILauncherProcess process, LauncherProcessSnapshot snapshot)
    {
        var current = process.GetSnapshot();
        return current.Pid == snapshot.Pid
            && string.Equals(current.ExecutablePath, snapshot.ExecutablePath, StringComparison.OrdinalIgnoreCase)
            && current.CreateTimeUtc == snapshot.CreateTimeUtc;
    }

    private LauncherLaunchRequest BuildLaunchRequest()
    {
        var arguments = new[]
        {
            _layout.BackendEntrypointPath,
            "--install-root",
            _layout.InstallRoot,
            "--user-data-root",
            _layout.UserDataRoot,
            "--host",
            _config.Backend.Host,
            "--port",
            _config.Backend.Port.ToString(CultureInfo.InvariantCulture),
            "--shutdown-request-path",
            _layout.ShutdownRequestPath,
            "--rpa-runtime-path",
            _layout.RpaRuntimeExecutable,
        };

        return new LauncherLaunchRequest(
            _layout.BackendPythonExecutable,
            _layout.InstallRoot,
            arguments,
            BuildPackagedEnvironment(),
            BuildCommandLineArguments(new[] { _layout.BackendPythonExecutable }.Concat(arguments)),
            Path.Combine(_layout.LogRoot, "backend.stdout.log"),
            Path.Combine(_layout.LogRoot, "backend.stderr.log"));
    }

    private async Task WaitForHealthAsync(ILauncherProcess process, CancellationToken cancellationToken)
    {
        var deadline = _clock.UtcNow.AddSeconds(_config.Backend.StartupTimeoutSeconds);
        while (_clock.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (await _httpProbeClient.CheckHealthAsync(_config.Backend.HealthUri, cancellationToken).ConfigureAwait(false))
            {
                return;
            }

            if (process.HasExited)
            {
                await process.WaitForExitAsync(TimeSpan.FromSeconds(1), cancellationToken).ConfigureAwait(false);
                throw CreateStartupFailure(process, backendStillRunning: false);
            }

            await _clock.Delay(PollInterval, cancellationToken).ConfigureAwait(false);
        }

        throw CreateStartupFailure(process, backendStillRunning: !process.HasExited);
    }

    private async Task WaitForRuntimeReadyAsync(CancellationToken cancellationToken)
    {
        var deadline = _clock.UtcNow.AddSeconds(_config.Backend.StartupTimeoutSeconds);
        while (_clock.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var observation = await ObserveRuntimeStatusAsync(cancellationToken).ConfigureAwait(false);
            if (observation.IsReady)
            {
                return;
            }

            await _clock.Delay(PollInterval, cancellationToken).ConfigureAwait(false);
        }

        throw new LauncherUserFacingException(
            $"Desktop runtime did not become ready within {_config.Backend.StartupTimeoutSeconds} seconds.");
    }

    private async Task<LauncherRuntimeObservation> ObserveRuntimeStatusAsync(CancellationToken cancellationToken)
    {
        var observation = await _httpProbeClient
            .GetRuntimeStatusAsync(_config.Backend.RuntimeStatusUri, cancellationToken)
            .ConfigureAwait(false);
        _lastObservation = observation;
        return observation;
    }

    private LauncherUserFacingException CreateStartupFailure(ILauncherProcess process, bool backendStillRunning)
    {
        var snapshot = _ownedSnapshot ?? process.GetSnapshot();
        var request = _ownedLaunchRequest ?? BuildLaunchRequest();
        var ownership = _portOwnershipProbe.Inspect(_config.Backend.Port, snapshot);
        if (ownership.OwnedByOtherProcess)
        {
            return CreatePortConflictFailure(ownership);
        }

        var details = BuildStartupFailureDetails(process, request, snapshot, ownership);
        var error = backendStillRunning
            ? new LauncherUserFacingException(
                LauncherText.BackendHealthTimeout(_config.Backend.StartupTimeoutSeconds, details),
                LauncherExitCodes.BackendHealthTimeout,
                "BACKEND_HEALTH_TIMEOUT")
            : new LauncherUserFacingException(
                LauncherText.BackendExitedEarly(details),
                LauncherExitCodes.BackendExitedEarly,
                "BACKEND_EXITED_EARLY");
        AppendLauncherLog(error.Message);
        return error;
    }

    private void ThrowIfConfiguredPortOwnedByOtherProcess()
    {
        var ownership = _portOwnershipProbe.Inspect(
            _config.Backend.Port,
            new LauncherProcessSnapshot(-1, string.Empty, DateTimeOffset.MinValue));
        if (ownership.OwnedByOtherProcess
            || (ownership.IsListening && !ownership.OwnedByCurrentProcess))
        {
            throw CreatePortConflictFailure(ownership);
        }
    }

    private LauncherUserFacingException CreatePortConflictFailure(LauncherPortOwnershipReport ownership)
    {
        var portConflict = new LauncherUserFacingException(
            LauncherText.PortConflict(_config.Backend.Port, ownership.OwningPid, ownership.OwningExecutablePath),
            LauncherExitCodes.PortOwnedByOtherProcess,
            "PORT_OWNED_BY_OTHER_PROCESS");
        AppendLauncherLog(portConflict.Message);
        return portConflict;
    }

    private LauncherUserFacingException CreateBackendStartFailure(LauncherLaunchRequest request, Exception ex)
    {
        var details = new LauncherStartupFailureDetails(
            BackendPid: null,
            ExitCode: null,
            ExecutablePath: request.ExecutablePath,
            CommandLine: request.CommandLine,
            StandardOutputPath: request.StandardOutputPath,
            StandardErrorPath: request.StandardErrorPath,
            LastErrorSummary: ex.Message);
        return new LauncherUserFacingException(
            LauncherText.BackendStartFailed(details),
            LauncherExitCodes.BackendStartFailed,
            "BACKEND_START_FAILED",
            ex);
    }

    private LauncherStartupFailureDetails BuildStartupFailureDetails(
        ILauncherProcess process,
        LauncherLaunchRequest request,
        LauncherProcessSnapshot snapshot,
        LauncherPortOwnershipReport ownership)
    {
        var stderrSummary = ReadLastSummaryLine(request.StandardErrorPath);
        var stdoutSummary = ReadLastSummaryLine(request.StandardOutputPath);
        var lastSummary = !string.IsNullOrWhiteSpace(stderrSummary)
            ? stderrSummary
            : !string.IsNullOrWhiteSpace(stdoutSummary)
                ? stdoutSummary
                : ownership.OwnedByOtherProcess
                    ? $"Port {_config.Backend.Port} is owned by pid {ownership.OwningPid}."
                    : "No backend stderr summary was captured.";
        return new LauncherStartupFailureDetails(
            BackendPid: snapshot.Pid,
            ExitCode: process.ExitCode,
            ExecutablePath: snapshot.ExecutablePath,
            CommandLine: request.CommandLine,
            StandardOutputPath: request.StandardOutputPath,
            StandardErrorPath: request.StandardErrorPath,
            LastErrorSummary: lastSummary);
    }

    private string ReadLastSummaryLine(string path)
    {
        if (!_fileSystem.FileExists(path))
        {
            return string.Empty;
        }

        var lines = _fileSystem.ReadAllText(path)
            .Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries);
        return lines.LastOrDefault(static line => !string.IsNullOrWhiteSpace(line)) ?? string.Empty;
    }

    private void EnsureWorkingDirectories()
    {
        _fileSystem.CreateDirectory(_layout.UserDataRoot);
        _fileSystem.CreateDirectory(_layout.DataRoot);
        _fileSystem.CreateDirectory(_layout.RuntimeRoot);
        _fileSystem.CreateDirectory(_layout.LogRoot);
    }

    private void WriteShutdownRequest(string reason)
    {
        var payload = JsonSerializer.Serialize(
            new
            {
                action = "shutdown",
                reason,
                requestedAtUtc = _clock.UtcNow,
            },
            JsonOptions);
        _fileSystem.WriteAllText(_layout.ShutdownRequestPath, payload);
    }

    private void PersistLauncherState(LauncherProcessSnapshot? snapshot)
    {
        var statePath = Path.Combine(_layout.RuntimeRoot, "launcher-state.json");
        var state = new LauncherState(
            LauncherContracts.SchemaVersion,
            _clock.UtcNow,
            snapshot is null
                ? null
                : new LauncherOwnedBackendState(
                    snapshot.Pid,
                    snapshot.CreateTimeUtc.ToString("O", CultureInfo.InvariantCulture),
                    snapshot.ExecutablePath,
                    Guid.NewGuid().ToString("N")),
            new LauncherStateUrls(
                _config.Backend.BackendBaseUri.ToString(),
                _config.Backend.HealthUri.ToString(),
                _config.Backend.RuntimeStatusUri.ToString()),
            new LauncherStateSafety(false, false));
        _fileSystem.WriteAllText(statePath, JsonSerializer.Serialize(state, JsonOptions));
    }

    private void AppendLauncherLog(string message)
    {
        var logPath = Path.Combine(_layout.LogRoot, "launcher.log");
        var line = $"{_clock.UtcNow:O} {message}{Environment.NewLine}";
        if (_fileSystem.FileExists(logPath))
        {
            _fileSystem.WriteAllText(logPath, _fileSystem.ReadAllText(logPath) + line);
            return;
        }

        _fileSystem.WriteAllText(logPath, line);
    }

    private bool ResolveLegacyPathExists(string pathPattern)
    {
        if (!pathPattern.StartsWith("%LOCALAPPDATA%", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var suffix = pathPattern["%LOCALAPPDATA%".Length..].TrimStart('\\');
        var candidate = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            suffix);
        return _fileSystem.DirectoryExists(candidate) || _fileSystem.FileExists(candidate);
    }

    private static void WriteArchiveEntry(ZipArchive archive, string entryName, string content)
    {
        var entry = archive.CreateEntry(entryName);
        using var writer = new StreamWriter(entry.Open(), Encoding.UTF8, leaveOpen: false);
        writer.Write(content);
    }
}

internal sealed class DefaultLauncherProcessLauncher : ILauncherProcessLauncher
{
    public ILauncherProcess Start(LauncherLaunchRequest request)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = request.ExecutablePath,
            WorkingDirectory = request.WorkingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        foreach (var argument in request.Arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        foreach (var pair in request.Environment)
        {
            startInfo.Environment[pair.Key] = pair.Value;
        }

        var process = Process.Start(startInfo)
            ?? throw new InvalidOperationException("Process.Start returned null for the packaged backend.");
        return new DefaultLauncherProcess(
            process,
            request.ExecutablePath,
            request.StandardOutputPath,
            request.StandardErrorPath);
    }
}

internal sealed class DefaultLauncherProcess : ILauncherProcess
{
    private readonly Process _process;
    private readonly string _expectedExecutablePath;
    private readonly string _stdoutPath;
    private readonly string _stderrPath;
    private readonly Task<string> _stdoutTask;
    private readonly Task<string> _stderrTask;
    private int _outputFlushed;

    public DefaultLauncherProcess(
        Process process,
        string expectedExecutablePath,
        string stdoutPath,
        string stderrPath)
    {
        _process = process;
        _expectedExecutablePath = Path.GetFullPath(expectedExecutablePath);
        _stdoutPath = stdoutPath;
        _stderrPath = stderrPath;
        _stdoutTask = _process.StandardOutput.ReadToEndAsync();
        _stderrTask = _process.StandardError.ReadToEndAsync();
    }

    public bool HasExited => _process.HasExited;

    public int? ExitCode => _process.HasExited ? _process.ExitCode : null;

    public LauncherProcessSnapshot GetSnapshot()
    {
        return new LauncherProcessSnapshot(
            _process.Id,
            _expectedExecutablePath,
            _process.StartTime.ToUniversalTime());
    }

    public async Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken)
    {
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        linkedCts.CancelAfter(timeout);
        try
        {
            await _process.WaitForExitAsync(linkedCts.Token).ConfigureAwait(false);
            await FlushOutputAsync().ConfigureAwait(false);
            return true;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            if (_process.HasExited)
            {
                await FlushOutputAsync().ConfigureAwait(false);
            }
            return _process.HasExited;
        }
    }

    public void KillTree()
    {
        if (_process.HasExited)
        {
            return;
        }

        _process.Kill(entireProcessTree: true);
    }

    public void Dispose()
    {
        _process.Dispose();
    }

    private async Task FlushOutputAsync()
    {
        if (Interlocked.Exchange(ref _outputFlushed, 1) != 0)
        {
            return;
        }

        Directory.CreateDirectory(Path.GetDirectoryName(_stdoutPath)!);
        Directory.CreateDirectory(Path.GetDirectoryName(_stderrPath)!);
        await File.WriteAllTextAsync(_stdoutPath, await _stdoutTask.ConfigureAwait(false), Encoding.UTF8).ConfigureAwait(false);
        await File.WriteAllTextAsync(_stderrPath, await _stderrTask.ConfigureAwait(false), Encoding.UTF8).ConfigureAwait(false);
    }
}

internal sealed class DefaultLauncherPortOwnershipProbe : ILauncherPortOwnershipProbe
{
    public LauncherPortOwnershipReport Inspect(int port, LauncherProcessSnapshot ownedSnapshot)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "netstat.exe",
                Arguments = "-ano -p tcp",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var process = Process.Start(startInfo);
            if (process is null)
            {
                return new LauncherPortOwnershipReport(false, false, false, null, string.Empty);
            }

            var output = process.StandardOutput.ReadToEnd();
            process.WaitForExit();

            var listeners = output
                .Split(new[] { "\r\n", "\n" }, StringSplitOptions.RemoveEmptyEntries)
                .Select(ParseNetstatLine)
                .Where(static entry => entry.HasValue)
                .Select(static entry => entry!.Value)
                .Where(entry => entry.Port == port)
                .ToList();
            if (listeners.Count == 0)
            {
                return new LauncherPortOwnershipReport(false, false, false, null, string.Empty);
            }

            var current = listeners.FirstOrDefault(entry => entry.Pid == ownedSnapshot.Pid);
            if (current != default)
            {
                return new LauncherPortOwnershipReport(true, true, false, current.Pid, ResolveExecutablePath(current.Pid));
            }

            var other = listeners[0];
            return new LauncherPortOwnershipReport(true, false, true, other.Pid, ResolveExecutablePath(other.Pid));
        }
        catch
        {
            return new LauncherPortOwnershipReport(false, false, false, null, string.Empty);
        }
    }

    private static (int Port, int Pid)? ParseNetstatLine(string rawLine)
    {
        var line = rawLine.Trim();
        if (!line.StartsWith("TCP", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        var parts = line
            .Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length < 5 || !string.Equals(parts[3], "LISTENING", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        var local = parts[1];
        var lastColon = local.LastIndexOf(':');
        if (lastColon < 0
            || !int.TryParse(local[(lastColon + 1)..], NumberStyles.Integer, CultureInfo.InvariantCulture, out var port)
            || !int.TryParse(parts[4], NumberStyles.Integer, CultureInfo.InvariantCulture, out var pid))
        {
            return null;
        }

        return (port, pid);
    }

    private static string ResolveExecutablePath(int pid)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            return process.MainModule?.FileName ?? string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }
}

internal sealed class DefaultLauncherHttpProbeClient : ILauncherHttpProbeClient
{
    private readonly HttpClient _client = new();

    public async Task<bool> CheckHealthAsync(Uri uri, CancellationToken cancellationToken)
    {
        try
        {
            using var response = await _client.GetAsync(uri, cancellationToken).ConfigureAwait(false);
            return response.IsSuccessStatusCode;
        }
        catch
        {
            return false;
        }
    }

    public async Task<LauncherRuntimeObservation> GetRuntimeStatusAsync(Uri uri, CancellationToken cancellationToken)
    {
        using var response = await _client.GetAsync(uri, cancellationToken).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        var payload = JsonDocument.Parse(await response.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false));
        var root = payload.RootElement;
        var status = root.TryGetProperty("status", out var statusElement) ? statusElement.GetString() ?? "unknown" : "unknown";
        var runtimeReachable = root.TryGetProperty("runtime_reachable", out var reachableElement)
            && reachableElement.ValueKind == JsonValueKind.True;
        var sendEnabled = root.TryGetProperty("send_enabled", out var sendElement)
            && sendElement.ValueKind == JsonValueKind.True;
        return new LauncherRuntimeObservation(status, runtimeReachable, sendEnabled);
    }
}

internal sealed class DefaultLauncherBrowserLauncher : ILauncherBrowserLauncher
{
    public void Open(Uri uri)
    {
        Process.Start(new ProcessStartInfo
        {
            FileName = uri.ToString(),
            UseShellExecute = true,
        });
    }
}

internal sealed class DefaultLauncherFileSystem : ILauncherFileSystem
{
    public bool FileExists(string path) => File.Exists(path);

    public bool DirectoryExists(string path) => Directory.Exists(path);

    public void CreateDirectory(string path) => Directory.CreateDirectory(path);

    public void DeleteFile(string path)
    {
        if (File.Exists(path))
        {
            File.Delete(path);
        }
    }

    public void WriteAllText(string path, string contents) => File.WriteAllText(path, contents, Encoding.UTF8);

    public string ReadAllText(string path) => File.ReadAllText(path, Encoding.UTF8);

    public byte[] ReadAllBytes(string path) => File.ReadAllBytes(path);

    public long GetFileSize(string path) => new FileInfo(path).Length;
}

internal sealed class DefaultLauncherClock : ILauncherClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;

    public Task Delay(TimeSpan delay, CancellationToken cancellationToken) => Task.Delay(delay, cancellationToken);
}
