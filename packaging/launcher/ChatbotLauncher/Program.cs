using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Windows.Forms;

namespace ChatbotLauncher;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
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
