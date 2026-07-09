from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
WINDOWS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\r\n\"']+")
BUILD_MACHINE_HINT_RE = re.compile(r"\\Desktop\\bot\\", re.IGNORECASE)
DESKTOP_BACKUP_HINT_RE = re.compile(r"\\WeChat Files\\", re.IGNORECASE)
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".key", ".pfx"}
TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".ps1",
    ".py",
    ".cs",
    ".csv",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_allowlist(allowlist_path: Path) -> dict[str, list[str]]:
    payload = json.loads(allowlist_path.read_text(encoding="utf-8"))
    return {
        "pathContains": payload.get("pathContains", []),
        "contentContains": payload.get("contentContains", []),
    }


def _normalize_relative(path: Path, bundle_root: Path) -> str:
    return path.relative_to(bundle_root).as_posix()


def _is_allowlisted_path(relative_path: str, allowlist: dict[str, list[str]]) -> bool:
    return any(token in relative_path for token in allowlist["pathContains"])


def _is_allowlisted_match(match_text: str, allowlist: dict[str, list[str]]) -> bool:
    return any(token in match_text for token in allowlist["contentContains"])


def _is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES and path.stat().st_size <= 2 * 1024 * 1024


def _build_finding(finding_type: str, relative_path: str, detail: str) -> dict[str, Any]:
    return {
        "type": finding_type,
        "severity": "error",
        "path": relative_path,
        "detail": detail,
    }


def scan_release_tree(bundle_root: Path, allowlist_path: Path) -> dict[str, Any]:
    bundle_root = bundle_root.resolve()
    allowlist = _load_allowlist(allowlist_path.resolve())
    findings: list[dict[str, Any]] = []
    seen_findings: set[tuple[str, str, str]] = set()
    file_count = 0

    def add_finding(finding_type: str, relative_path: str, detail: str) -> None:
        key = (finding_type, relative_path, detail)
        if key in seen_findings:
            return
        seen_findings.add(key)
        findings.append(_build_finding(finding_type, relative_path, detail))

    for file_path in sorted(bundle_root.rglob("*")):
        if not file_path.is_file():
            continue
        file_count += 1
        relative_path = _normalize_relative(file_path, bundle_root)
        if _is_allowlisted_path(relative_path, allowlist):
            continue

        suffix = file_path.suffix.lower()
        if suffix in FORBIDDEN_SUFFIXES:
            add_finding("forbidden_file", relative_path, f"Forbidden packaged file suffix detected: {suffix}")

        if not _is_text_candidate(file_path):
            continue

        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for match in WINDOWS_PATH_RE.findall(text):
            if _is_allowlisted_match(match, allowlist):
                continue
            if BUILD_MACHINE_HINT_RE.search(match):
                add_finding("build_machine_path", relative_path, "Build-machine path content detected and redacted.")
            elif DESKTOP_BACKUP_HINT_RE.search(match):
                add_finding("desktop_backup_path", relative_path, "Desktop backup path content detected and redacted.")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "bundleRootName": bundle_root.name,
        "generatedAtUtc": _utc_now(),
        "summary": {
            "fileCount": file_count,
            "findingCount": len(findings),
            "blocked": bool(findings),
        },
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-root", required=True)
    parser.add_argument("--allowlist", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    report = scan_release_tree(Path(args.bundle_root), Path(args.allowlist))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if report["summary"]["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
