from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
BYTECODE_SUFFIXES = {".pyc", ".pyo"}
STRIP_FILE_NAMES = {"direct_url.json", "RECORD"}
STRIP_SUFFIXES = {".pdb", ".map"}
RPA_BUILD_ROOT = Path("runtime/desktop-rpa/resources/app.asar.unpacked/node_modules")
RPA_BUILD_PRUNE_SUFFIXES = {
    ".cc",
    ".cmd",
    ".exp",
    ".filters",
    ".gypi",
    ".iobj",
    ".lib",
    ".mk",
    ".props",
    ".recipe",
    ".rsp",
    ".sln",
    ".targets",
    ".tlog",
    ".vcxproj",
}
RPA_BUILD_PRUNE_NAMES = {
    "binding.Makefile",
    "config.gypi",
    "project.sln",
    "project.vcxproj",
    "project.vcxproj.filters",
}


def _build_literal_replacement(value: str) -> bytes:
    encoded = value.encode("utf-8")
    marker = f"<REDACTED:{len(encoded)}>".encode("ascii")
    if len(marker) > len(encoded):
        marker = marker[: len(encoded)]
    return marker.ljust(len(encoded), b"_")


def _normalize_token(token: str) -> str:
    return token.strip().replace("/", "\\")


def _default_blocked_literals(repo_root: Path | None, user_profile: Path | None) -> list[str]:
    literals = [
        r"C:\Users\runneradmin",
        r"file:///C:/actions-runner/",
        r"C:/actions-runner/",
    ]
    if repo_root is not None:
        literals.append(str(repo_root.resolve(strict=False)))
    if user_profile is not None:
        user_profile_value = str(user_profile.resolve(strict=False))
        literals.append(user_profile_value)
        literals.append(str((user_profile / "Desktop" / "wechat-decrypt.backup").resolve(strict=False)))
    return literals


def _should_strip_metadata_file(path: Path) -> bool:
    if path.suffix.lower() in BYTECODE_SUFFIXES | STRIP_SUFFIXES:
        return True
    if path.name in STRIP_FILE_NAMES and any(part.endswith(".dist-info") for part in path.parts):
        return True
    return False


def _is_rpa_build_artifact(relative_path: Path) -> bool:
    try:
        relative_path.relative_to(RPA_BUILD_ROOT)
    except ValueError:
        return False
    if relative_path.suffix.lower() == ".node":
        return False
    if relative_path.name.endswith(".lastbuildstate"):
        return True
    if relative_path.name in RPA_BUILD_PRUNE_NAMES:
        return True
    if relative_path.suffix.lower() in RPA_BUILD_PRUNE_SUFFIXES:
        return True
    return any(part.endswith(".tlog") for part in relative_path.parts)


def _delete_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        for child in sorted(path.iterdir(), reverse=True):
            _delete_path(child)
        path.rmdir()
        return
    path.unlink()


def sanitize_bundle(
    bundle_root: Path,
    *,
    repo_root: Path | None = None,
    user_profile: Path | None = None,
    extra_blocked_literals: list[str] | None = None,
) -> dict[str, Any]:
    bundle_root = bundle_root.resolve(strict=False)
    removed: list[str] = []
    redacted: list[str] = []

    blocked_literals = _default_blocked_literals(repo_root, user_profile)
    if extra_blocked_literals:
        blocked_literals.extend(extra_blocked_literals)

    normalized_literals = []
    seen_literals = set()
    for literal in blocked_literals:
        normalized = _normalize_token(literal)
        if not normalized or normalized in seen_literals:
            continue
        seen_literals.add(normalized)
        normalized_literals.append(normalized)

    replacement_pairs = [
        (literal.encode("utf-8"), _build_literal_replacement(literal))
        for literal in normalized_literals
    ]

    file_paths = sorted(path for path in bundle_root.rglob("*") if path.is_file())
    for path in file_paths:
        relative_path = path.relative_to(bundle_root)
        if _should_strip_metadata_file(path) or _is_rpa_build_artifact(relative_path):
            path.unlink(missing_ok=True)
            removed.append(relative_path.as_posix())

    for directory in sorted((path for path in bundle_root.rglob("*") if path.is_dir()), reverse=True):
        relative_path = directory.relative_to(bundle_root)
        if directory.name == "__pycache__":
            _delete_path(directory)
            removed.append(relative_path.as_posix() + "/")
            continue
        if _is_rpa_build_artifact(relative_path) and not any(directory.iterdir()):
            directory.rmdir()

    for path in sorted(candidate for candidate in bundle_root.rglob("*") if candidate.is_file()):
        original = path.read_bytes()
        updated = original
        for old_bytes, new_bytes in replacement_pairs:
            updated = updated.replace(old_bytes, new_bytes)
        if updated != original:
            path.write_bytes(updated)
            redacted.append(path.relative_to(bundle_root).as_posix())

    remaining_bytecode = [
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_file() and path.suffix.lower() in BYTECODE_SUFFIXES
    ]
    remaining_pycache = [
        path.relative_to(bundle_root).as_posix()
        for path in bundle_root.rglob("*")
        if path.is_dir() and path.name == "__pycache__"
    ]

    return {
        "schemaVersion": SCHEMA_VERSION,
        "bundleRootName": bundle_root.name,
        "removed": removed,
        "redacted": redacted,
        "remainingBytecodeFiles": remaining_bytecode,
        "remainingPycacheDirectories": remaining_pycache,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--user-profile", default="")
    parser.add_argument("--blocked-literal", action="append", default=[])
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    report = sanitize_bundle(
        Path(args.bundle_root),
        repo_root=Path(args.repo_root) if args.repo_root else None,
        user_profile=Path(args.user_profile) if args.user_profile else None,
        extra_blocked_literals=args.blocked_literal,
    )

    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if report["remainingBytecodeFiles"] or report["remainingPycacheDirectories"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
