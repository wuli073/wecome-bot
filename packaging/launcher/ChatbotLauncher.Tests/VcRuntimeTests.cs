using ChatbotLauncher;
using Xunit;

namespace ChatbotLauncher.Tests;

public sealed class VcRuntimeTests
{
    [Fact]
    public void VcRuntimeProbe_ReadsInstalledRegistryState()
    {
        var policy = CreatePolicy(
            registry: new FakeRegistryReader(installed: 1, version: "14.44.35211.0"));

        var probe = policy.Probe();

        Assert.True(probe.IsInstalled);
        Assert.Equal("14.44.35211.0", probe.Version);
    }

    [Fact]
    public void VcRuntimeSetupInstalledFlow_DoesNotLaunchPortableInstallerFallback()
    {
        var fileSystem = new FakeLauncherFileSystem();
        var prompt = new FakePrompt();
        var installer = new FakeInstallerLauncher();
        var policy = CreatePolicy(
            fileSystem: fileSystem,
            prompt: prompt,
            installer: installer);
        var layout = LauncherInstallationLayout.CreateDefault(
            @"C:\Users\Alice\AppData\Local\Programs\Chatbot",
            @"C:\Users\Alice\AppData\Local");

        var result = policy.EnsureAvailable(layout);

        Assert.Equal(VcRuntimeCheckStatus.MissingForSetupInstalledFlow, result.Status);
        Assert.Equal(0, prompt.Invocations);
        Assert.Equal(0, installer.Invocations);
    }

    [Fact]
    public void VcRuntimePortableFlow_RecordsCancellationAndBlocksRepeatedElevationPrompt()
    {
        var fileSystem = new FakeLauncherFileSystem();
        var prompt = new FakePrompt(confirm: true);
        var installer = new FakeInstallerLauncher(new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.UacCancelled, 1223));
        var policy = CreatePolicy(
            fileSystem: fileSystem,
            prompt: prompt,
            installer: installer);
        var layout = LauncherInstallationLayout.CreateDefault(
            @"C:\Portable\Chatbot",
            @"C:\Users\Alice\AppData\Local");
        fileSystem.AddFile(Path.Combine(layout.InstallRoot, "prerequisites", "vc_redist.x64.exe"), "binary");

        var first = policy.EnsureAvailable(layout);
        var second = policy.EnsureAvailable(layout);

        Assert.Equal(VcRuntimeCheckStatus.UacCancelled, first.Status);
        Assert.Equal(VcRuntimeCheckStatus.RetryBlocked, second.Status);
        Assert.Equal(1, prompt.Invocations);
        Assert.Equal(1, installer.Invocations);
    }

    [Fact]
    public void VcRuntimePortableFlow_ReturnsClearMissingBinaryError()
    {
        var policy = CreatePolicy();
        var layout = LauncherInstallationLayout.CreateDefault(
            @"C:\Portable\Chatbot",
            @"C:\Users\Alice\AppData\Local");

        var result = policy.EnsureAvailable(layout);

        Assert.Equal(VcRuntimeCheckStatus.MissingInstallerBinary, result.Status);
        Assert.Contains("vc_redist.x64.exe", result.Message);
    }

    private static VcRuntimeLaunchPolicy CreatePolicy(
        FakeRegistryReader? registry = null,
        FakeLauncherFileSystem? fileSystem = null,
        FakePrompt? prompt = null,
        FakeInstallerLauncher? installer = null)
    {
        return new VcRuntimeLaunchPolicy(
            registry ?? new FakeRegistryReader(installed: 0, version: string.Empty),
            fileSystem ?? new FakeLauncherFileSystem(),
            prompt ?? new FakePrompt(confirm: true),
            installer ?? new FakeInstallerLauncher(new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.Installed, 0)),
            new FakeClock());
    }

    private sealed class FakeRegistryReader : IVcRuntimeRegistryReader
    {
        private readonly int _installed;
        private readonly string _version;

        public FakeRegistryReader(int installed, string version)
        {
            _installed = installed;
            _version = version;
        }

        public int? ReadDword(string subKeyPath, string valueName)
        {
            return valueName == "Installed" ? _installed : null;
        }

        public string? ReadString(string subKeyPath, string valueName)
        {
            return valueName == "Version" ? _version : null;
        }
    }

    private sealed class FakePrompt : IVcRuntimePrompt
    {
        private readonly bool _confirm;

        public FakePrompt(bool confirm = false)
        {
            _confirm = confirm;
        }

        public int Invocations { get; private set; }

        public bool ConfirmPortableFallback(string message)
        {
            Invocations += 1;
            return _confirm;
        }
    }

    private sealed class FakeInstallerLauncher : IVcRuntimeInstallerLauncher
    {
        private readonly VcRuntimeInstallerResult _result;

        public FakeInstallerLauncher(VcRuntimeInstallerResult? result = null)
        {
            _result = result ?? new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.Installed, 0);
        }

        public int Invocations { get; private set; }

        public VcRuntimeInstallerResult Launch(string installerPath)
        {
            Invocations += 1;
            return _result;
        }
    }

    private sealed class FakeLauncherFileSystem : ILauncherFileSystem
    {
        private readonly Dictionary<string, string> _files = new(StringComparer.OrdinalIgnoreCase);
        private readonly HashSet<string> _directories = new(StringComparer.OrdinalIgnoreCase);

        public void AddFile(string path, string content)
        {
            _files[path] = content;
        }

        public bool FileExists(string path) => _files.ContainsKey(path);

        public bool DirectoryExists(string path) => _directories.Contains(path);

        public void CreateDirectory(string path)
        {
            _directories.Add(path);
        }

        public void DeleteFile(string path)
        {
            _files.Remove(path);
        }

        public void MoveFile(string sourcePath, string destinationPath)
        {
            _files[destinationPath] = _files[sourcePath];
            _files.Remove(sourcePath);
        }

        public void WriteAllText(string path, string contents)
        {
            _files[path] = contents;
        }

        public string ReadAllText(string path)
        {
            return _files[path];
        }

        public byte[] ReadAllBytes(string path)
        {
            return System.Text.Encoding.UTF8.GetBytes(_files[path]);
        }

        public long GetFileSize(string path)
        {
            return ReadAllBytes(path).LongLength;
        }
    }

    private sealed class FakeClock : ILauncherClock
    {
        public DateTimeOffset UtcNow => DateTimeOffset.Parse("2026-07-10T00:00:00Z");

        public Task Delay(TimeSpan delay, CancellationToken cancellationToken) => Task.CompletedTask;
    }
}
