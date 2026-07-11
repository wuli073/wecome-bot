using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using ChatbotLauncher;
using Xunit;

namespace ChatbotLauncher.Tests;

public sealed class ManifestValidatorTests
{
    [Fact]
    public void ValidateInstallation_ThrowsWhenManifestIsMissing()
    {
        using var fixture = new ManifestFixture();

        var error = Assert.Throws<LauncherUserFacingException>(() => fixture.Manager.ValidateInstallation());

        Assert.Contains("manifest.json", error.Message);
    }

    [Fact]
    public void ValidateInstallation_ThrowsWhenCriticalFileIsMissing()
    {
        using var fixture = new ManifestFixture();
        fixture.WriteManifest();
        File.Delete(Path.Combine(fixture.Layout.InstallRoot, "ChatbotLauncher.exe"));

        var error = Assert.Throws<LauncherUserFacingException>(() => fixture.Manager.ValidateInstallation());

        Assert.Contains("ChatbotLauncher.exe", error.Message);
    }

    [Fact]
    public void ValidateInstallation_ThrowsWhenCriticalShaDoesNotMatch()
    {
        using var fixture = new ManifestFixture();
        fixture.WriteManifest();
        File.WriteAllText(Path.Combine(fixture.Layout.InstallRoot, "ChatbotLauncher.exe"), "tampered", Encoding.UTF8);

        var error = Assert.Throws<LauncherUserFacingException>(() => fixture.Manager.ValidateInstallation());

        Assert.Contains("SHA-256", error.Message);
    }

    [Fact]
    public void ValidateInstallation_UsesQuickValidationForNonCriticalFiles()
    {
        using var fixture = new ManifestFixture();
        fixture.WriteManifest();
        var nonCriticalPath = Path.Combine(fixture.Layout.InstallRoot, "logs", "readme.txt");
        var originalSize = new FileInfo(nonCriticalPath).Length;
        File.WriteAllBytes(nonCriticalPath, Enumerable.Repeat((byte)'x', (int)originalSize).ToArray());

        fixture.Manager.ValidateInstallation();
    }

    private sealed class ManifestFixture : IDisposable
    {
        private readonly string _root;

        public ManifestFixture()
        {
            _root = Path.Combine(Path.GetTempPath(), $"chatbot-launcher-manifest-{Guid.NewGuid():N}");
            Layout = LauncherInstallationLayout.CreateDefault(Path.Combine(_root, "Chatbot"), Path.Combine(_root, "LocalAppData"));
            CreateLayoutFiles();
            Manager = LauncherProcessManager.CreateDefault(
                new LauncherConfig(
                    LauncherContracts.SchemaVersion,
                    new LauncherBackendConfig("127.0.0.1", 5302, "/healthz", "/api/v1/desktop-automation/runtime/status", 30)),
                Layout);
        }

        public LauncherInstallationLayout Layout { get; }

        public LauncherProcessManager Manager { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        public void WriteManifest()
        {
            var manifestPath = Path.Combine(Layout.InstallRoot, "manifest.json");
            var entries = new[]
            {
                BuildEntry("ChatbotLauncher.exe", critical: true),
                BuildEntry(@"server\runtime\python\python.exe", critical: true),
                BuildEntry(@"server\app\packaging\server\entrypoint.py", critical: true),
                BuildEntry(@"connectors\runtime\python\python.exe", critical: true),
                BuildEntry(@"connectors\app\wechat-decrypt\connector_runtime.py", critical: true),
                BuildEntry(@"runtime\desktop-rpa\LangBot Desktop RPA Runtime.exe", critical: true),
                BuildEntry(@"resources\web\dist\index.html", critical: true),
                BuildEntry(@"logs\readme.txt", critical: false),
            };
            var payload = new
            {
                schemaVersion = 1,
                nonCriticalValidation = "size",
                entries,
            };
            File.WriteAllText(manifestPath, JsonSerializer.Serialize(payload), Encoding.UTF8);
        }

        private void CreateLayoutFiles()
        {
            Directory.CreateDirectory(Layout.InstallRoot);
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "server", "runtime", "python"));
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "server", "app", "packaging", "server"));
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "connectors", "runtime", "python"));
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "connectors", "app", "wechat-decrypt"));
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "runtime", "desktop-rpa"));
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "resources", "web", "dist"));
            Directory.CreateDirectory(Path.Combine(Layout.InstallRoot, "logs"));

            File.WriteAllText(Path.Combine(Layout.InstallRoot, "launcher.json"), "{}", Encoding.UTF8);
            File.WriteAllText(Path.Combine(Layout.InstallRoot, "ChatbotLauncher.exe"), "launcher", Encoding.UTF8);
            File.WriteAllText(Layout.BackendPythonExecutable, "python", Encoding.UTF8);
            File.WriteAllText(Layout.BackendEntrypointPath, "entrypoint", Encoding.UTF8);
            File.WriteAllText(Layout.ConnectorPythonExecutable, "python", Encoding.UTF8);
            File.WriteAllText(Layout.ConnectorRuntimeScriptPath, "connector", Encoding.UTF8);
            File.WriteAllText(Layout.RpaRuntimeExecutable, "rpa", Encoding.UTF8);
            File.WriteAllText(Path.Combine(Layout.InstallRoot, "resources", "web", "dist", "index.html"), "<html></html>", Encoding.UTF8);
            File.WriteAllText(Path.Combine(Layout.InstallRoot, "logs", "readme.txt"), "placeholder content here!", Encoding.UTF8);
        }

        private object BuildEntry(string relativePath, bool critical)
        {
            var fullPath = Path.Combine(Layout.InstallRoot, relativePath);
            var bytes = File.ReadAllBytes(fullPath);
            return new
            {
                path = relativePath.Replace('\\', '/'),
                critical,
                size = bytes.Length,
                sha256 = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
            };
        }
    }
}
