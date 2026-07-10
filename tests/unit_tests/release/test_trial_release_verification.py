from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-trial-release.ps1"
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "test-trial-install.ps1"
MATRIX = REPO_ROOT / "docs" / "release" / "verification-matrix.md"
ALLOWED_STATUSES = {"PASS", "FAIL", "BLOCKED", "UNVERIFIED"}


@pytest.fixture()
def repo_tmp_path() -> Path:
    root = REPO_ROOT / "build" / "pytest-temp" / "task17-verification"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=root))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_under_root(root: Path, candidate: Path) -> bool:
    root_resolved = root.resolve(strict=False)
    candidate_resolved = candidate.resolve(strict=False)
    try:
        candidate_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise AssertionError(f"path escaped root: {candidate_resolved}") from exc
    return True


def _validate_manifest_hashes(release_root: Path) -> None:
    manifest = json.loads((release_root / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["entries"]:
        rel = Path(entry["path"])
        if rel.is_absolute() or ".." in rel.parts:
            raise AssertionError(f"unsafe manifest path: {entry['path']}")
        file_path = release_root / rel
        _assert_under_root(release_root, file_path)
        assert file_path.exists(), entry["path"]
        if entry.get("critical") is True:
            assert _sha256(file_path) == entry["sha256"]


def _build_minimized_path(release_root: Path, system_root: Path) -> str:
    parts = [
        system_root / "System32",
        system_root,
        system_root / "System32" / "WindowsPowerShell" / "v1.0",
        release_root / "server" / "runtime" / "python",
        release_root / "connectors" / "runtime" / "python",
        release_root / "runtime" / "desktop-rpa",
        release_root,
    ]
    return ";".join(str(part) for part in parts)


def _reject_system_tool_path(executable: Path, release_root: Path, allowed_runtime: str) -> None:
    _assert_under_root(release_root / allowed_runtime, executable)


def _redact_sensitive_paths(text: str) -> str:
    text = re.sub(r"[A-Za-z]:\\Users\\[^\r\n\"']+", "<ABSOLUTE_PATH>", text)
    text = re.sub(r"(?i)(token|password|secret|authorization)(\s*[:=]\s*)[^\r\n;]+", r"\1\2[REDACTED]", text)
    return text


def _is_user_data_retained_after_uninstall(user_data_root: Path, install_root: Path) -> bool:
    return user_data_root.exists() and not (install_root / "ChatbotLauncher.exe").exists()


def test_powershell_scripts_parse_without_syntax_errors() -> None:
    command = (
        "$ErrorActionPreference='Stop';"
        "foreach($p in @('scripts/verify-trial-release.ps1','scripts/test-trial-install.ps1')) {"
        "$tokens=$null;$errors=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $p),[ref]$tokens,[ref]$errors) > $null;"
        "if($errors.Count -gt 0){ throw (($errors | ForEach-Object Message) -join '; ') }"
        "}"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )


def test_manifest_sha_validation_fails_on_corrupted_critical_file(repo_tmp_path: Path) -> None:
    release_root = repo_tmp_path / "Chatbot-Trial-0.1.0-x64"
    release_root.mkdir()
    launcher = release_root / "ChatbotLauncher.exe"
    launcher.write_text("original", encoding="utf-8")
    manifest = {
        "schemaVersion": 1,
        "version": "0.1.0",
        "entries": [
            {"path": "ChatbotLauncher.exe", "size": launcher.stat().st_size, "sha256": _sha256(launcher), "critical": True}
        ],
    }
    (release_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    launcher.write_text("corrupted", encoding="utf-8")
    with pytest.raises(AssertionError):
        _validate_manifest_hashes(release_root)


def test_minimized_path_excludes_development_tool_segments() -> None:
    release_root = Path(r"C:\release\Chatbot-Trial-0.1.0-x64")
    value = _build_minimized_path(release_root, Path(r"C:\Windows"))
    for forbidden in [
        r"C:\Users\dev\AppData\Local\Programs\Python",
        r"C:\Program Files\nodejs",
        r"C:\Users\dev\AppData\Roaming\npm",
        r"C:\Program Files\Git\cmd",
        r"C:\Users\dev\.cargo\bin\uv.exe",
    ]:
        assert forbidden.lower() not in value.lower()
    assert str(release_root / "server" / "runtime" / "python") in value
    assert str(release_root / "connectors" / "runtime" / "python") in value


def test_release_path_containment_rejects_escape(repo_tmp_path: Path) -> None:
    root = repo_tmp_path / "release"
    root.mkdir()
    _assert_under_root(root, root / "server" / "runtime")
    with pytest.raises(AssertionError):
        _assert_under_root(root, repo_tmp_path / "outside" / "python.exe")


def test_system_python_and_connector_runtime_path_checks(repo_tmp_path: Path) -> None:
    release_root = repo_tmp_path / "release"
    connector_python = release_root / "connectors" / "runtime" / "python" / "python.exe"
    server_python = release_root / "server" / "runtime" / "python" / "python.exe"
    system_python = repo_tmp_path / "Python312" / "python.exe"
    _reject_system_tool_path(connector_python, release_root, "connectors/runtime")
    _reject_system_tool_path(server_python, release_root, "server/runtime")
    with pytest.raises(AssertionError):
        _reject_system_tool_path(system_python, release_root, "server/runtime")


def test_status_enum_and_unverified_reporting_are_constrained() -> None:
    matrix = MATRIX.read_text(encoding="utf-8")
    statuses = set(re.findall(r"\| [^|]+ \| [^|]+ \| (PASS|FAIL|BLOCKED|UNVERIFIED) ", matrix))
    assert statuses
    assert statuses <= ALLOWED_STATUSES
    assert "UNVERIFIED" in statuses
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")
    assert "ValidateSet(\"PASS\", \"FAIL\", \"UNVERIFIED\")" in verify_script
    assert "ValidateSet(\"PASS\", \"FAIL\", \"UNVERIFIED\")" in install_script


def test_sensitive_path_and_secret_redaction() -> None:
    raw = "token=abcdefghijklmnopqrstuvwxyz\n" + r"C:\Users\33031\Desktop\bot\secret.txt"
    redacted = _redact_sensitive_paths(raw)
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted
    assert r"C:\Users\33031\Desktop\bot\secret.txt" not in redacted
    assert "[REDACTED]" in redacted
    assert "<ABSOLUTE_PATH>" in redacted


def test_installer_root_and_user_data_retention_logic(repo_tmp_path: Path) -> None:
    install_root = repo_tmp_path / "Chatbot Trial Install"
    user_data_root = repo_tmp_path / "LocalAppData" / "Chatbot"
    install_root.mkdir()
    user_data_root.mkdir(parents=True)
    (install_root / "ChatbotLauncher.exe").write_text("launcher", encoding="utf-8")
    assert not _is_user_data_retained_after_uninstall(user_data_root, install_root)
    (install_root / "ChatbotLauncher.exe").unlink()
    assert _is_user_data_retained_after_uninstall(user_data_root, install_root)


def test_task17_scripts_cover_required_release_safety_terms() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")
    for term in [
        "LANGBOT_BROADCAST_SEND_ENABLED",
        "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS",
        "LANGBOT_RPA_ALLOW_AUTO_SEND",
        "LANGBOT_RPA_FORCE_DISABLE_SEND",
        "connectors\\runtime",
        "server\\runtime",
        "runtime\\desktop-rpa",
        "port-conflict",
        "no-residual-processes",
    ]:
        assert term in verify_script
    for term in ["UpgradeSetupPath", "uninstall-user-data-retention", "vc_redist", "Shortcut"]:
        assert term in install_script
