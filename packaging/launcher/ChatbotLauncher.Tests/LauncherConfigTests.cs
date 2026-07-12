using ChatbotLauncher;
using Xunit;

namespace ChatbotLauncher.Tests;

public sealed class LauncherConfigTests
{
    [Fact]
    public void TemplateConfig_ParsesTask1ContractRoutesAndDefaults()
    {
        var config = LauncherConfig.LoadFromFile(GetProjectFilePath("launcher.json"));

        Assert.Equal(LauncherContracts.SchemaVersion, config.SchemaVersion);
        Assert.Equal("127.0.0.1", config.Backend.Host);
        Assert.Equal(5302, config.Backend.Port);
        Assert.Equal("/healthz", config.Backend.HealthPath);
        Assert.Equal("/api/v1/system/runtime/status", config.Backend.RuntimeStatusPath);
        Assert.Equal(60, config.Backend.StartupTimeoutSeconds);
        Assert.Equal(new Uri("http://127.0.0.1:5302/healthz"), config.Backend.HealthUri);
        Assert.Equal(
            new Uri("http://127.0.0.1:5302/api/v1/system/runtime/status"),
            config.Backend.RuntimeStatusUri);
    }

    [Theory]
    [InlineData("0.0.0.0")]
    [InlineData("localhost")]
    [InlineData("127.0.0.2")]
    public void Parse_RejectsInvalidHost(string host)
    {
        var json = $$"""
            {
              "schemaVersion": 1,
              "backend": {
                "host": "{{host}}",
                "port": 5302,
                "healthPath": "/healthz",
                "runtimeStatusPath": "/api/v1/system/runtime/status",
                "startupTimeoutSeconds": 60
              }
            }
            """;

        var error = Assert.Throws<InvalidOperationException>(() => LauncherConfig.Parse(json));

        Assert.Contains("127.0.0.1", error.Message);
    }

    [Theory]
    [InlineData(0)]
    [InlineData(65536)]
    public void Parse_RejectsInvalidPort(int port)
    {
        var json = $$"""
            {
              "schemaVersion": 1,
              "backend": {
                "host": "127.0.0.1",
                "port": {{port}},
                "healthPath": "/healthz",
                "runtimeStatusPath": "/api/v1/system/runtime/status",
                "startupTimeoutSeconds": 60
              }
            }
            """;

        var error = Assert.Throws<InvalidOperationException>(() => LauncherConfig.Parse(json));

        Assert.Contains("between 1 and 65535", error.Message);
    }

    [Fact]
    public void LauncherStateSchema_ReferencesPackagedRuntimeStatePath()
    {
        var schema = File.ReadAllText(GetProjectFilePath("launcher-state.schema.json"));

        Assert.Contains("%LOCALAPPDATA%\\\\\\\\Chatbot\\\\\\\\runtime\\\\\\\\launcher-state.json", schema);
    }

    private static string GetProjectFilePath(string fileName)
    {
        return Path.GetFullPath(Path.Combine(
            AppContext.BaseDirectory,
            "..",
            "..",
            "..",
            "..",
            "ChatbotLauncher",
            fileName));
    }
}
