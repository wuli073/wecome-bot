using System.Security.Cryptography;
using System.Text.Json;
using ChatbotLauncher;
using Xunit;

namespace ChatbotLauncher.Tests;

public sealed class LifecycleTests
{
    [Fact]
    public void BuildPackagedEnvironment_UsesDefaultDisabledSendValues()
    {
        var manager = CreateManager();

        var environment = manager.BuildPackagedEnvironment();

        Assert.Equal("0", environment["LANGBOT_BROADCAST_SEND_ENABLED"]);
        Assert.Equal(string.Empty, environment["LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS"]);
        Assert.Equal("0", environment["LANGBOT_RPA_ALLOW_AUTO_SEND"]);
        Assert.Equal("1", environment["LANGBOT_RPA_FORCE_DISABLE_SEND"]);
    }

    [Fact]
    public async Task StartAsync_UsesConfiguredHealthAndRuntimeStatusPathsAndOpensBrowserAfterReadiness()
    {
        var http = new FakeHttpProbeClient
        {
        };
        http.HealthResponses.Enqueue(false);
        http.HealthResponses.Enqueue(true);
        http.RuntimeResponses.Enqueue(new LauncherRuntimeObservation("starting", false, false));
        http.RuntimeResponses.Enqueue(new LauncherRuntimeObservation("ready", true, false));
        var browser = new FakeBrowserLauncher();
        var process = new FakeProcess();
        var launcher = new FakeProcessLauncher(process);
        var manager = CreateManager(
            backend: new LauncherBackendConfig("127.0.0.1", 5302, "/custom-health", "/custom-runtime", 30),
            http: http,
            browser: browser,
            processLauncher: launcher);

        await manager.StartAsync();

        Assert.Equal(2, http.HealthRequests.Count);
        Assert.All(http.HealthRequests, request => Assert.Equal(new Uri("http://127.0.0.1:5302/custom-health"), request));
        Assert.Equal(new Uri("http://127.0.0.1:5302/custom-runtime"), http.RuntimeRequests.Last());
        Assert.Equal(new Uri("http://127.0.0.1:5302/"), Assert.Single(browser.OpenedUris));
        Assert.NotNull(manager.LastObservation);
        Assert.True(manager.LastObservation!.IsReady);
    }

    [Fact]
    public async Task StartAsync_ThrowsUserFacingPortConflictWhenBackendExitsBeforeHealthReady()
    {
        var http = new FakeHttpProbeClient
        {
        };
        http.HealthResponses.Enqueue(false);
        var process = new FakeProcess { HasExitedValue = true };
        var manager = CreateManager(
            http: http,
            processLauncher: new FakeProcessLauncher(process));

        var error = await Assert.ThrowsAsync<LauncherUserFacingException>(() => manager.StartAsync());

        Assert.Contains("5302", error.Message);
    }

    [Fact]
    public async Task StopAsync_OnlyForceKillsOwnedProcessWhenIdentityMatches()
    {
        var process = new FakeProcess
        {
            WaitForExitResult = false,
        };
        var manager = CreateManager(
            processLauncher: new FakeProcessLauncher(process),
            http: ReadyHttpClient());
        await manager.StartAsync();

        process.ExecutablePath = @"C:\unexpected\python.exe";
        await manager.StopAsync();

        Assert.False(process.KillTreeCalled);
    }

    [Fact]
    public async Task StopAsync_ForceKillsOwnedProcessAfterTimeoutWhenIdentityStillMatches()
    {
        var process = new FakeProcess
        {
            WaitForExitResult = false,
        };
        var manager = CreateManager(
            processLauncher: new FakeProcessLauncher(process),
            http: ReadyHttpClient());
        await manager.StartAsync();

        await manager.StopAsync();

        Assert.True(process.KillTreeCalled);
    }

    private static FakeHttpProbeClient ReadyHttpClient()
    {
        var http = new FakeHttpProbeClient();
        http.HealthResponses.Enqueue(true);
        http.RuntimeResponses.Enqueue(new LauncherRuntimeObservation("ready", true, false));
        return http;
    }

    private static LauncherProcessManager CreateManager(
        LauncherBackendConfig? backend = null,
        FakeHttpProbeClient? http = null,
        FakeBrowserLauncher? browser = null,
        FakeProcessLauncher? processLauncher = null)
    {
        var config = new LauncherConfig(
            LauncherContracts.SchemaVersion,
            backend ?? new LauncherBackendConfig(
                "127.0.0.1",
                5302,
                "/healthz",
                "/api/v1/desktop-automation/runtime/status",
                30));
        var layout = LauncherInstallationLayout.CreateDefault(
            @"C:\Chatbot",
            @"C:\Users\Alice\AppData\Local");
        var fileSystem = new FakeFileSystem(layout);
        return new LauncherProcessManager(
            config,
            layout,
            processLauncher ?? new FakeProcessLauncher(new FakeProcess()),
            http ?? ReadyHttpClient(),
            browser ?? new FakeBrowserLauncher(),
            fileSystem,
            new FakeClock());
    }

    private sealed class FakeProcessLauncher : ILauncherProcessLauncher
    {
        private readonly FakeProcess _process;

        public FakeProcessLauncher(FakeProcess process)
        {
            _process = process;
        }

        public ILauncherProcess Start(LauncherLaunchRequest request)
        {
            _process.ExecutablePath = request.ExecutablePath;
            return _process;
        }
    }

    private sealed class FakeProcess : ILauncherProcess
    {
        public bool HasExitedValue { get; set; }

        public bool KillTreeCalled { get; private set; }

        public bool WaitForExitResult { get; set; } = true;

        public string ExecutablePath { get; set; } = @"C:\Chatbot\server\runtime\python\python.exe";

        public DateTimeOffset CreateTimeUtc { get; set; } = DateTimeOffset.Parse("2026-07-10T00:00:00Z");

        public bool HasExited => HasExitedValue;

        public LauncherProcessSnapshot GetSnapshot()
        {
            return new LauncherProcessSnapshot(4242, ExecutablePath, CreateTimeUtc);
        }

        public Task<bool> WaitForExitAsync(TimeSpan timeout, CancellationToken cancellationToken)
        {
            return Task.FromResult(WaitForExitResult);
        }

        public void KillTree()
        {
            KillTreeCalled = true;
        }

        public void Dispose()
        {
        }
    }

    private sealed class FakeHttpProbeClient : ILauncherHttpProbeClient
    {
        public Queue<bool> HealthResponses { get; } = new();

        public Queue<LauncherRuntimeObservation> RuntimeResponses { get; } = new();

        public List<Uri> HealthRequests { get; } = new();

        public List<Uri> RuntimeRequests { get; } = new();

        public Task<bool> CheckHealthAsync(Uri uri, CancellationToken cancellationToken)
        {
            HealthRequests.Add(uri);
            return Task.FromResult(HealthResponses.Count > 0 ? HealthResponses.Dequeue() : true);
        }

        public Task<LauncherRuntimeObservation> GetRuntimeStatusAsync(Uri uri, CancellationToken cancellationToken)
        {
            RuntimeRequests.Add(uri);
            return Task.FromResult(RuntimeResponses.Count > 0
                ? RuntimeResponses.Dequeue()
                : new LauncherRuntimeObservation("ready", true, false));
        }
    }

    private sealed class FakeBrowserLauncher : ILauncherBrowserLauncher
    {
        public List<Uri> OpenedUris { get; } = new();

        public void Open(Uri uri)
        {
            OpenedUris.Add(uri);
        }
    }

    private sealed class FakeFileSystem : ILauncherFileSystem
    {
        private readonly HashSet<string> _files = new(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _directories = new(StringComparer.OrdinalIgnoreCase);
        private readonly Dictionary<string, string> _contents = new(StringComparer.OrdinalIgnoreCase);

        public FakeFileSystem(LauncherInstallationLayout layout)
        {
            foreach (var artifact in layout.GetRequiredArtifacts())
            {
                if (artifact.Directory)
                {
                    _directories.Add(artifact.Path);
                }
                else
                {
                    _files.Add(artifact.Path);
                    _contents[artifact.Path] = artifact.Description;
                }
            }

            _files.Add(Path.Combine(layout.InstallRoot, "launcher.json"));
            _contents[Path.Combine(layout.InstallRoot, "launcher.json")] = "{}";

            var manifestEntries = new List<object>();
            foreach (var filePath in _files)
            {
                if (string.Equals(filePath, Path.Combine(layout.InstallRoot, "manifest.json"), StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                var relativePath = Path.GetRelativePath(layout.InstallRoot, filePath).Replace('\\', '/');
                manifestEntries.Add(new
                {
                    path = relativePath,
                    size = GetFileSize(filePath),
                    sha256 = ComputeSha256(_contents[filePath]),
                    critical = true,
                });
            }

            var manifestPath = Path.Combine(layout.InstallRoot, "manifest.json");
            _files.Add(manifestPath);
            _contents[manifestPath] = JsonSerializer.Serialize(new
            {
                schemaVersion = LauncherContracts.SchemaVersion,
                nonCriticalValidation = "size",
                entries = manifestEntries,
            });
        }

        public bool FileExists(string path) => _files.Contains(path);

        public bool DirectoryExists(string path) => _directories.Contains(path);

        public void CreateDirectory(string path)
        {
            _directories.Add(path);
        }

        public void DeleteFile(string path)
        {
            _files.Remove(path);
            _contents.Remove(path);
        }

        public void WriteAllText(string path, string contents)
        {
            _files.Add(path);
            _contents[path] = contents;
        }

        public string ReadAllText(string path)
        {
            return _contents.TryGetValue(path, out var content) ? content : string.Empty;
        }

        public byte[] ReadAllBytes(string path)
        {
            return System.Text.Encoding.UTF8.GetBytes(ReadAllText(path));
        }

        public long GetFileSize(string path)
        {
            return ReadAllBytes(path).LongLength;
        }

        private static string ComputeSha256(string value)
        {
            return Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value))).ToLowerInvariant();
        }
    }

    private sealed class FakeClock : ILauncherClock
    {
        private DateTimeOffset _now = DateTimeOffset.Parse("2026-07-10T00:00:00Z");

        public DateTimeOffset UtcNow => _now;

        public Task Delay(TimeSpan delay, CancellationToken cancellationToken)
        {
            _now = _now.Add(delay);
            return Task.CompletedTask;
        }
    }
}
