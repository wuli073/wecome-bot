import json
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'packaging' / 'runtime-manifest.json'
REQUIRED_ROLE_KEYS = (
    'provider',
    'version',
    'url',
    'sha256',
    'archiveType',
    'artifactName',
)


def load_manifest() -> dict:
    if not MANIFEST.exists():
        raise SystemExit(f'missing manifest: {MANIFEST}')
    try:
        return json.loads(MANIFEST.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise SystemExit(f'invalid JSON in {MANIFEST}: {exc}') from exc


def validate_cache(cache: dict) -> None:
    for key in (
        'root',
        'archivesDir',
        'extractedDir',
        'offlineRequiresCacheHit',
        'onlineDownloadPolicy',
        'offlinePolicy',
    ):
        if key not in cache:
            raise SystemExit(f'cache.{key} is required')

    if not isinstance(cache['offlineRequiresCacheHit'], bool):
        raise SystemExit('cache.offlineRequiresCacheHit must be a boolean')

    if Path(str(cache['root'])).is_absolute():
        raise SystemExit('cache.root must be a repository-relative path')


def validate_role(role: str, entry: dict) -> None:
    for key in REQUIRED_ROLE_KEYS:
        if not entry.get(key):
            raise SystemExit(f'{role}.{key} is required')

    url = str(entry['url'])
    lowered_url = url.lower()
    if lowered_url.endswith('/latest') or 'latest' in lowered_url:
        raise SystemExit(f'{role}.url must not be floating/latest')

    sha256 = str(entry['sha256']).lower()
    if sha256 in {'', 'latest'} or len(sha256) != 64:
        raise SystemExit(f'{role}.sha256 must be a fixed 64-character SHA-256')
    if any(ch not in '0123456789abcdef' for ch in sha256):
        raise SystemExit(f'{role}.sha256 must contain only hexadecimal characters')

    artifact_name = str(entry['artifactName'])
    parsed_name = Path(unquote(urlparse(url).path)).name
    if artifact_name != parsed_name:
        raise SystemExit(f'{role}.artifactName must match the URL filename')

    extracted_layout = entry.get('extractedLayout')
    if not isinstance(extracted_layout, dict):
        raise SystemExit(f'{role}.extractedLayout is required')
    for key in ('rootDir', 'pythonExe', 'pythonwExe', 'licenseFile'):
        if not extracted_layout.get(key):
            raise SystemExit(f'{role}.extractedLayout.{key} is required')

    site_packages = entry.get('sitePackages')
    if not isinstance(site_packages, dict):
        raise SystemExit(f'{role}.sitePackages is required')
    for key in ('relativePath', 'activation', 'installCommand'):
        if not site_packages.get(key):
            raise SystemExit(f'{role}.sitePackages.{key} is required')

    if entry.get('pipIncludedUpstream') not in {True, False}:
        raise SystemExit(f'{role}.pipIncludedUpstream must be a boolean')
    if not entry.get('licenseFileSource'):
        raise SystemExit(f'{role}.licenseFileSource is required')


def main() -> None:
    data = load_manifest()

    if data.get('schemaVersion') != 1:
        raise SystemExit('schemaVersion must be 1')

    cache = data.get('cache')
    if not isinstance(cache, dict):
        raise SystemExit('cache is required')
    validate_cache(cache)

    for role in ('server', 'connector'):
        entry = data.get(role) or {}
        validate_role(role, entry)

    print('runtime manifest verified')


if __name__ == '__main__':
    main()
