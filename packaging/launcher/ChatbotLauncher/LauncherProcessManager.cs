using System.Diagnostics;
using System.Globalization;
using System.IO.Compression;
using System.Text;
using System.Text.Json;

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
    public static LauncherInstallationLayout CreateDefault(string installRoot, string? localAppData = null)
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

        var userDataRoot = Path.Combine(resolvedLocalAppData, "Chatbot");
        var runtimeRoot = Path.Combine(userDataRoot, "runtime");
        var logRoot = Path.Combine(userDataRoot, "logs");
        var dataRoot = Path.Combine(userDataRoot, "data");
        var resourcesRoot = Path.Combine(resolvedInstallRoot, "resources");

        return new LauncherInstallationLayout(
            InstallRoot: resolvedInstallRoot,
            UserDataRoot: userDataRoot,
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
    IReadOnlyDictionary<string, string> Environment);

public sealed record LauncherProcessSnapshot(int Pid, string ExecutablePath, DateTimeOffset CreateTimeUtc);

public sealed record LauncherRuntimeObservation(string Status, bool RuntimeReachable, bool SendEnabled)
{
    public bool IsReady =>
        RuntimeReachable || string.Equals(Status, "ready", StringComparison.OrdinalIgnoreCase);
}

public interface ILauncherProcess : IDisposable
{
    bool HasExited { get; }

    LauncherProcessSnapshot GetSnapshot();

    Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken);

    void KillTree();
}

public interface ILauncherProcessLauncher
{
    ILauncherProcess Start(LauncherLaunchRequest request);
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
}

public interface ILauncherClock
{
    DateTimeOffset UtcNow { get; }

    Task Delay(TimeSpan delay, CancellationToken cancellationToken);
}

public sealed class LauncherUserFacingException : Exception
{
    public LauncherUserFacingException(string message)
        : base(message)
    {
    }
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
    private readonly ILauncherFileSystem _fileSystem;
    private readonly ILauncherClock _clock;
    private readonly object _sync = new();

    private ILauncherProcess? _ownedProcess;
    private LauncherProcessSnapshot? _ownedSnapshot;
    private LauncherRuntimeObservation? _lastObservation;

    public LauncherProcessManager(
        LauncherConfig config,
        LauncherInstallationLayout layout,
        ILauncherProcessLauncher processLauncher,
        ILauncherHttpProbeClient httpProbeClient,
        ILauncherBrowserLauncher browserLauncher,
        ILauncherFileSystem fileSystem,
        ILauncherClock clock)
    {
        _config = config;
        _layout = layout;
        _processLauncher = processLauncher;
        _httpProbeClient = httpProbeClient;
        _browserLauncher = browserLauncher;
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
            new DefaultLauncherFileSystem(),
            new DefaultLauncherClock());
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

        var request = BuildLaunchRequest();
        AppendLauncherLog($"Starting packaged backend: {request.ExecutablePath} {string.Join(' ', request.Arguments)}");
        var process = _processLauncher.Start(request);
        var snapshot = process.GetSnapshot();

        lock (_sync)
        {
            _ownedProcess = process;
            _ownedSnapshot = snapshot;
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
        return new LauncherLaunchRequest(
            _layout.BackendPythonExecutable,
            _layout.InstallRoot,
            new[]
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
            },
            BuildPackagedEnvironment());
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
                throw new LauncherUserFacingException(LauncherText.PortConflict(_config.Backend.Port));
            }

            await _clock.Delay(PollInterval, cancellationToken).ConfigureAwait(false);
        }

        throw new LauncherUserFacingException(
            $"Backend did not become healthy within {_config.Backend.StartupTimeoutSeconds} seconds.");
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
            ?? throw new LauncherUserFacingException("Failed to start the packaged backend process.");
        return new DefaultLauncherProcess(process, request.ExecutablePath);
    }
}

internal sealed class DefaultLauncherProcess : ILauncherProcess
{
    private readonly Process _process;
    private readonly string _expectedExecutablePath;

    public DefaultLauncherProcess(Process process, string expectedExecutablePath)
    {
        _process = process;
        _expectedExecutablePath = Path.GetFullPath(expectedExecutablePath);
    }

    public bool HasExited => _process.HasExited;

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
            return true;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
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
}

internal sealed class DefaultLauncherClock : ILauncherClock
{
    public DateTimeOffset UtcNow => DateTimeOffset.UtcNow;

    public Task Delay(TimeSpan delay, CancellationToken cancellationToken) => Task.Delay(delay, cancellationToken);
}
