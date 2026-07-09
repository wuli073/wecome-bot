using ChatbotLauncher;
using Xunit;

namespace ChatbotLauncher.Tests;

public sealed class DiagnosticsTests
{
    [Fact]
    public void BuildDefinition_RecordsLegacyDirectoryCheckWithoutMigration()
    {
        var definition = LauncherDiagnostics.BuildDefinition();

        Assert.Equal(LauncherContracts.SchemaVersion, definition.SchemaVersion);
        Assert.Contains(definition.BundleEntries, entry => entry.RelativePath == "launcher.json" && entry.Required);
        var legacy = Assert.Single(definition.LegacyDirectoryChecks);
        Assert.Equal("legacy-wecomebot-user-data", legacy.LogicalName);
        Assert.Equal(@"%LOCALAPPDATA%\WecomeBot", legacy.PathPattern);
        Assert.Contains("must never be auto-migrated", legacy.Note);
    }

    [Fact]
    public void RedactText_RedactsSecretsAndAbsolutePaths()
    {
        const string installRoot = @"C:\Program Files\Chatbot";
        const string userDataRoot = @"C:\Users\Alice\AppData\Local\Chatbot";
        var raw = string.Join(Environment.NewLine, new[]
        {
            "{\"token\":\"abc123\",\"status\":\"ok\"}",
            "Authorization: Bearer xyz987",
            "password = super-secret",
            $@"install={installRoot}\server\app\main.py",
            $@"userData={userDataRoot}\runtime\launcher-state.json",
            @"other=C:\BuildAgent\work\1\s\artifact.txt",
        });

        var result = LauncherDiagnostics.RedactText(raw, new LauncherDiagnosticsContext(installRoot, userDataRoot));

        Assert.DoesNotContain("abc123", result.RedactedText, StringComparison.Ordinal);
        Assert.DoesNotContain("xyz987", result.RedactedText, StringComparison.Ordinal);
        Assert.DoesNotContain("super-secret", result.RedactedText, StringComparison.Ordinal);
        Assert.DoesNotContain(installRoot, result.RedactedText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(userDataRoot, result.RedactedText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(@"C:\BuildAgent\work\1\s\artifact.txt", result.RedactedText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("%INSTALL_ROOT%\\server\\app\\main.py", result.RedactedText);
        Assert.Contains("%USER_DATA_ROOT%\\runtime\\launcher-state.json", result.RedactedText);
        Assert.Contains("<ABSOLUTE_PATH>", result.RedactedText);
        Assert.Contains("json-secret-values", result.AppliedRules);
        Assert.Contains("assignment-secret-values", result.AppliedRules);
        Assert.Contains("install-root-paths", result.AppliedRules);
        Assert.Contains("user-data-root-paths", result.AppliedRules);
        Assert.Contains("absolute-paths", result.AppliedRules);
    }
}
