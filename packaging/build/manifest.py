from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
GENERATED_FILES = {
    "manifest.json",
    "SHA256SUMS.txt",
    "build-report.json",
    "build-sensitive-scan.json",
}
CRITICAL_EXACT_PATHS = {
    "ChatbotLauncher.exe",
    "launcher.json",
    "server/runtime/python/python.exe",
    "server/app/packaging/server/entrypoint.py",
    "connectors/runtime/python/python.exe",
    "connectors/app/wechat-decrypt/connector_runtime.py",
    "resources/web/dist/index.html",
    "runtime/desktop-rpa/LangBot Desktop RPA Runtime.exe",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_relative(path: Path, bundle_root: Path) -> str:
    return path.relative_to(bundle_root).as_posix()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _should_include(path: Path, bundle_root: Path) -> bool:
    if not path.is_file():
        return False
    relative = _normalize_relative(path, bundle_root)
    return relative not in GENERATED_FILES


def _is_critical(relative_path: str) -> bool:
    return relative_path in CRITICAL_EXACT_PATHS


def build_manifest(bundle_root: Path, version: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle_root = bundle_root.resolve()
    entries: list[dict[str, Any]] = []
    for file_path in sorted(bundle_root.rglob("*")):
        if not _should_include(file_path, bundle_root):
            continue
        relative = _normalize_relative(file_path, bundle_root)
        entries.append(
            {
                "path": relative,
                "size": file_path.stat().st_size,
                "sha256": _sha256_file(file_path),
                "critical": _is_critical(relative),
            }
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "product": "Chatbot Trial",
        "architecture": "x64",
        "version": version,
        "generatedAtUtc": _utc_now(),
        "nonCriticalValidation": "sha256",
        "entries": entries,
        "metadata": metadata or {},
    }


def write_manifest_artifacts(
    bundle_root: Path,
    version: str,
    manifest_path: Path,
    sha256sums_path: Path,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    manifest = build_manifest(bundle_root=bundle_root, version=version, metadata=metadata)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [f'{entry["sha256"]} *{entry["path"]}' for entry in manifest["entries"]]
    sha256sums_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--sha256sums-path", required=True)
    parser.add_argument("--metadata-json", default="")
    parser.add_argument("--metadata-path", default="")
    args = parser.parse_args()

    if args.metadata_json and args.metadata_path:
        parser.error("--metadata-json and --metadata-path are mutually exclusive")
    metadata = json.loads(args.metadata_json) if args.metadata_json else {}
    if args.metadata_path:
        metadata = json.loads(Path(args.metadata_path).read_text(encoding="utf-8"))
    write_manifest_artifacts(
        bundle_root=Path(args.bundle_root),
        version=args.version,
        manifest_path=Path(args.manifest_path),
        sha256sums_path=Path(args.sha256sums_path),
        metadata=metadata,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
