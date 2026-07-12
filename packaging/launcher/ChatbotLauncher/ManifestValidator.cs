using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace ChatbotLauncher;

internal sealed class ManifestValidator
{
    private static readonly string[] GeneratedArtifactNames =
    {
        "manifest.json",
        "SHA256SUMS.txt",
        "build-report.json",
        "build-sensitive-scan.json",
    };

    private readonly ILauncherFileSystem _fileSystem;

    public ManifestValidator(ILauncherFileSystem fileSystem)
    {
        _fileSystem = fileSystem;
    }

    public void Validate(string installRoot)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(installRoot);

        var manifestPath = Path.Combine(installRoot, "manifest.json");
        if (!_fileSystem.FileExists(manifestPath))
        {
            throw new LauncherUserFacingException("Packaged installation is incomplete: missing manifest.json.");
        }

        var manifest = JsonSerializer.Deserialize(
                _fileSystem.ReadAllText(manifestPath),
                ManifestJsonContext.Default.LauncherManifestDocument)
            ?? throw new LauncherUserFacingException("manifest.json did not contain a manifest document.");

        if (manifest.SchemaVersion != LauncherContracts.SchemaVersion)
        {
            throw new LauncherUserFacingException(
                $"manifest schemaVersion must be {LauncherContracts.SchemaVersion}, got {manifest.SchemaVersion}.");
        }

        foreach (var entry in manifest.Entries)
        {
            var entryPath = ResolveEntryPath(installRoot, entry.Path);
            if (!_fileSystem.FileExists(entryPath))
            {
                throw new LauncherUserFacingException(
                    $"Packaged installation is incomplete: manifest entry missing ({entry.Path}).");
            }

            var actualSize = _fileSystem.GetFileSize(entryPath);
            if (actualSize != entry.Size)
            {
                throw new LauncherUserFacingException(
                    $"Manifest size mismatch for {entry.Path}. Expected {entry.Size}, got {actualSize}.");
            }

            if (entry.Critical || !string.Equals(manifest.NonCriticalValidation, "size", StringComparison.OrdinalIgnoreCase))
            {
                var actualSha256 = ComputeSha256(_fileSystem.ReadAllBytes(entryPath));
                if (!string.Equals(actualSha256, entry.Sha256, StringComparison.OrdinalIgnoreCase))
                {
                    throw new LauncherUserFacingException(
                        $"Manifest SHA-256 mismatch for {entry.Path}. Expected {entry.Sha256}, got {actualSha256}.");
                }
            }
        }

        var expectedPaths = manifest.Entries
            .Select(entry => ResolveEntryPath(installRoot, entry.Path))
            .Append(manifestPath)
            .Concat(GeneratedArtifactNames.Select(name => Path.Combine(installRoot, name)))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var extraFile = _fileSystem.EnumerateFiles(installRoot)
            .FirstOrDefault(path => !expectedPaths.Contains(path));
        if (extraFile is not null)
        {
            throw new LauncherUserFacingException(
                $"Packaged installation contains an extra file: {Path.GetRelativePath(installRoot, extraFile)}.");
        }
    }

    private static string ResolveEntryPath(string installRoot, string relativePath)
    {
        var resolvedInstallRoot = Path.GetFullPath(installRoot).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var combined = Path.GetFullPath(Path.Combine(resolvedInstallRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        if (!combined.StartsWith(resolvedInstallRoot + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
            && !string.Equals(combined, resolvedInstallRoot, StringComparison.OrdinalIgnoreCase))
        {
            throw new LauncherUserFacingException($"Manifest entry escapes install root: {relativePath}");
        }

        return combined;
    }

    private static string ComputeSha256(byte[] bytes)
    {
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }
}

internal sealed record LauncherManifestDocument(
    [property: JsonPropertyName("schemaVersion")] int SchemaVersion,
    [property: JsonPropertyName("nonCriticalValidation")] string NonCriticalValidation,
    [property: JsonPropertyName("entries")] IReadOnlyList<LauncherManifestEntry> Entries);

internal sealed record LauncherManifestEntry(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("size")] long Size,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonPropertyName("critical")] bool Critical);

[JsonSerializable(typeof(LauncherManifestDocument))]
internal partial class ManifestJsonContext : JsonSerializerContext;
