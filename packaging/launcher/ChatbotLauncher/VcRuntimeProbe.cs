using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.Win32;

namespace ChatbotLauncher;

public enum VcRuntimeCheckStatus
{
    Ready,
    MissingForSetupInstalledFlow,
    MissingInstallerBinary,
    UserDeclinedPortableFallback,
    UacCancelled,
    InstallFailed,
    RetryBlocked,
}

public enum VcRuntimeInstallerOutcome
{
    Installed,
    UacCancelled,
    Failed,
}

public sealed record VcRuntimeProbeResult(bool IsInstalled, string Version, string Source);

public sealed record VcRuntimeCheckResult(
    VcRuntimeCheckStatus Status,
    string Message,
    VcRuntimeProbeResult Probe,
    string? InstallerPath = null,
    int? ExitCode = null);

public sealed record VcRuntimeInstallerResult(VcRuntimeInstallerOutcome Outcome, int ExitCode);

public sealed record VcRuntimeFallbackAttempt(DateTimeOffset AttemptedAtUtc, VcRuntimeCheckStatus Status, string Message);

public interface IVcRuntimeRegistryReader
{
    int? ReadDword(string subKeyPath, string valueName);

    string? ReadString(string subKeyPath, string valueName);
}

public interface IVcRuntimePrompt
{
    bool ConfirmPortableFallback(string message);
}

public interface IVcRuntimeInstallerLauncher
{
    VcRuntimeInstallerResult Launch(string installerPath);
}

public sealed class VcRuntimeLaunchPolicy
{
    public const string RuntimeSubKeyPath = @"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64";

    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true,
    };

    private readonly IVcRuntimeRegistryReader _registryReader;
    private readonly ILauncherFileSystem _fileSystem;
    private readonly IVcRuntimePrompt _prompt;
    private readonly IVcRuntimeInstallerLauncher _installerLauncher;
    private readonly ILauncherClock _clock;

    public VcRuntimeLaunchPolicy(
        IVcRuntimeRegistryReader registryReader,
        ILauncherFileSystem fileSystem,
        IVcRuntimePrompt prompt,
        IVcRuntimeInstallerLauncher installerLauncher,
        ILauncherClock clock)
    {
        _registryReader = registryReader;
        _fileSystem = fileSystem;
        _prompt = prompt;
        _installerLauncher = installerLauncher;
        _clock = clock;
    }

    public static VcRuntimeLaunchPolicy CreateDefault(ILauncherFileSystem fileSystem, ILauncherClock clock)
    {
        return new VcRuntimeLaunchPolicy(
            new RegistryVcRuntimeReader(),
            fileSystem,
            new MessageBoxVcRuntimePrompt(),
            new ElevatedVcRuntimeInstallerLauncher(),
            clock);
    }

    public VcRuntimeProbeResult Probe()
    {
        var installed = _registryReader.ReadDword(RuntimeSubKeyPath, "Installed") ?? 0;
        var version = _registryReader.ReadString(RuntimeSubKeyPath, "Version") ?? string.Empty;
        return new VcRuntimeProbeResult(installed == 1, version, RuntimeSubKeyPath);
    }

    public VcRuntimeCheckResult EnsureAvailable(LauncherInstallationLayout layout)
    {
        var probe = Probe();
        if (probe.IsInstalled)
        {
            ClearPortableFallbackAttempt(layout);
            return new VcRuntimeCheckResult(VcRuntimeCheckStatus.Ready, "VC++ runtime is installed.", probe);
        }

        if (IsSetupInstalledFlow(layout.InstallRoot))
        {
            return new VcRuntimeCheckResult(
                VcRuntimeCheckStatus.MissingForSetupInstalledFlow,
                LauncherText.VcRuntimeMissingForInstalledFlow(),
                probe);
        }

        var previousAttempt = ReadPortableFallbackAttempt(layout);
        if (previousAttempt is not null)
        {
            return new VcRuntimeCheckResult(
                VcRuntimeCheckStatus.RetryBlocked,
                LauncherText.VcRuntimeRetryBlocked(previousAttempt.Status),
                probe);
        }

        var installerPath = Path.Combine(layout.InstallRoot, "prerequisites", "vc_redist.x64.exe");
        if (!_fileSystem.FileExists(installerPath))
        {
            PersistPortableFallbackAttempt(
                layout,
                new VcRuntimeFallbackAttempt(
                    _clock.UtcNow,
                    VcRuntimeCheckStatus.MissingInstallerBinary,
                    LauncherText.VcRuntimeInstallerMissing()));
            return new VcRuntimeCheckResult(
                VcRuntimeCheckStatus.MissingInstallerBinary,
                LauncherText.VcRuntimeInstallerMissing(),
                probe,
                installerPath);
        }

        if (!_prompt.ConfirmPortableFallback(LauncherText.VcRuntimePortablePrompt()))
        {
            PersistPortableFallbackAttempt(
                layout,
                new VcRuntimeFallbackAttempt(
                    _clock.UtcNow,
                    VcRuntimeCheckStatus.UserDeclinedPortableFallback,
                    LauncherText.VcRuntimePortableDeclined()));
            return new VcRuntimeCheckResult(
                VcRuntimeCheckStatus.UserDeclinedPortableFallback,
                LauncherText.VcRuntimePortableDeclined(),
                probe,
                installerPath);
        }

        var installResult = _installerLauncher.Launch(installerPath);
        if (installResult.Outcome == VcRuntimeInstallerOutcome.Installed)
        {
            ClearPortableFallbackAttempt(layout);
            return new VcRuntimeCheckResult(
                VcRuntimeCheckStatus.Ready,
                LauncherText.VcRuntimeInstalled(),
                probe,
                installerPath,
                installResult.ExitCode);
        }

        var failureStatus = installResult.Outcome == VcRuntimeInstallerOutcome.UacCancelled
            ? VcRuntimeCheckStatus.UacCancelled
            : VcRuntimeCheckStatus.InstallFailed;
        var failureMessage = installResult.Outcome == VcRuntimeInstallerOutcome.UacCancelled
            ? LauncherText.VcRuntimeUacCancelled()
            : LauncherText.VcRuntimeInstallFailed(installResult.ExitCode);
        PersistPortableFallbackAttempt(
            layout,
            new VcRuntimeFallbackAttempt(_clock.UtcNow, failureStatus, failureMessage));
        return new VcRuntimeCheckResult(
            failureStatus,
            failureMessage,
            probe,
            installerPath,
            installResult.ExitCode);
    }

    public static bool IsSetupInstalledFlow(string installRoot)
    {
        var normalizedInstallRoot = Path.GetFullPath(installRoot).TrimEnd('\\');
        if (normalizedInstallRoot.EndsWith(@"\Programs\Chatbot", StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        var defaultInstalledRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "Programs",
            "Chatbot");
        return normalizedInstallRoot.StartsWith(defaultInstalledRoot, StringComparison.OrdinalIgnoreCase);
    }

    private VcRuntimeFallbackAttempt? ReadPortableFallbackAttempt(LauncherInstallationLayout layout)
    {
        var statePath = GetPortableFallbackStatePath(layout);
        if (!_fileSystem.FileExists(statePath))
        {
            return null;
        }

        return JsonSerializer.Deserialize<VcRuntimeFallbackAttempt>(_fileSystem.ReadAllText(statePath), JsonOptions);
    }

    private void PersistPortableFallbackAttempt(LauncherInstallationLayout layout, VcRuntimeFallbackAttempt attempt)
    {
        var statePath = GetPortableFallbackStatePath(layout);
        _fileSystem.CreateDirectory(Path.GetDirectoryName(statePath)!);
        _fileSystem.WriteAllText(statePath, JsonSerializer.Serialize(attempt, JsonOptions));
    }

    private void ClearPortableFallbackAttempt(LauncherInstallationLayout layout)
    {
        _fileSystem.DeleteFile(GetPortableFallbackStatePath(layout));
    }

    private static string GetPortableFallbackStatePath(LauncherInstallationLayout layout)
    {
        return Path.Combine(layout.RuntimeRoot, "vc-runtime-fallback.json");
    }
}

internal sealed class RegistryVcRuntimeReader : IVcRuntimeRegistryReader
{
    public int? ReadDword(string subKeyPath, string valueName)
    {
        using var key = Registry.LocalMachine.OpenSubKey(subKeyPath);
        var value = key?.GetValue(valueName);
        return value switch
        {
            int intValue => intValue,
            _ => null,
        };
    }

    public string? ReadString(string subKeyPath, string valueName)
    {
        using var key = Registry.LocalMachine.OpenSubKey(subKeyPath);
        return key?.GetValue(valueName)?.ToString();
    }
}

internal sealed class MessageBoxVcRuntimePrompt : IVcRuntimePrompt
{
    public bool ConfirmPortableFallback(string message)
    {
        if (LauncherEnvironment.IsNonInteractive())
        {
            return false;
        }

        return MessageBox.Show(
            message,
            LauncherText.ErrorTitle(),
            MessageBoxButtons.YesNo,
            MessageBoxIcon.Warning) == DialogResult.Yes;
    }
}

internal sealed class ElevatedVcRuntimeInstallerLauncher : IVcRuntimeInstallerLauncher
{
    public VcRuntimeInstallerResult Launch(string installerPath)
    {
        try
        {
            var process = Process.Start(new ProcessStartInfo
            {
                FileName = installerPath,
                Arguments = "/install /quiet /norestart",
                UseShellExecute = true,
                Verb = "runas",
                WindowStyle = ProcessWindowStyle.Normal,
            });
            if (process is null)
            {
                return new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.Failed, -1);
            }

            process.WaitForExit();
            return process.ExitCode == 0
                ? new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.Installed, process.ExitCode)
                : new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.Failed, process.ExitCode);
        }
        catch (Win32Exception ex) when (ex.NativeErrorCode == 1223)
        {
            return new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.UacCancelled, ex.NativeErrorCode);
        }
        catch
        {
            return new VcRuntimeInstallerResult(VcRuntimeInstallerOutcome.Failed, -1);
        }
    }
}
