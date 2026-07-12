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


def _quote_windows_process_argument(value: str | None) -> str:
    """Mirror ConvertTo-ProcessArgument for focused, OS-independent test vectors."""
    if value is None or value == "":
        return '""'
    if not re.search(r'[\s"]', value):
        return value
    return '"' + re.sub(r"(\\+)$", lambda match: match.group(1) * 2, re.sub(r'(\\*)"', lambda match: match.group(1) * 2 + r'\"', value)) + '"'


def _classify_health_failure(
    *, launcher_started: bool, launcher_exited: bool, backend_pid_known: bool,
    backend_alive: bool, listening_pids: list[int], session_pids: list[int], http_status: int | None,
) -> str:
    if not launcher_started:
        return "LAUNCHER_NOT_STARTED"
    if launcher_exited:
        return "LAUNCHER_EXITED_EARLY"
    if not backend_pid_known:
        return "BACKEND_NOT_CREATED"
    if not backend_alive:
        return "BACKEND_EXITED_EARLY"
    if not listening_pids:
        return "PORT_NOT_LISTENING"
    if any(pid not in session_pids for pid in listening_pids):
        return "PORT_OWNED_BY_OTHER_PROCESS"
    if http_status is not None:
        return "HEALTH_HTTP_ERROR"
    return "BACKEND_HEALTH_TIMEOUT"


def _parse_launcher_state_backend(state: dict[str, object]) -> tuple[int, str, str, str]:
    backend = state.get("backend")
    if not isinstance(backend, dict):
        raise ValueError("LAUNCHER_STATE_SCHEMA_INVALID")
    pid = backend.get("pid")
    process_create_time_utc = backend.get("processCreateTimeUtc")
    executable_path = backend.get("executablePath")
    session_id = backend.get("sessionId")
    if not isinstance(pid, int):
        raise ValueError("LAUNCHER_STATE_SCHEMA_INVALID")
    if not all(isinstance(value, str) and value for value in [process_create_time_utc, executable_path, session_id]):
        raise ValueError("LAUNCHER_STATE_SCHEMA_INVALID")
    return pid, process_create_time_utc, executable_path, session_id


def _should_run_port_conflict(previous_stage_status: str) -> bool:
    return previous_stage_status == "PASS"


def _is_safe_residual_cleanup_candidate(
    *,
    executable_path: str | None,
    command_line: str | None,
    path_readable: bool,
    creation_time_matches: bool,
    launcher_state_matches: bool,
) -> bool:
    if not path_readable:
        return False
    text = f"{executable_path or ''}\n{command_line or ''}".lower()
    if launcher_state_matches or creation_time_matches:
        return True
    return "chatbot-trial-0.1.1-x64" in text or "chatbottrialverify" in text


def _select_runtime_ports(
    requested_runtime_port: int,
    requested_conflict_port: int,
    unavailable_ports: set[int],
) -> tuple[int, int]:
    def pick(preferred: int, used: set[int]) -> int:
        if preferred > 0:
            if preferred in used:
                raise ValueError("requested port already in use")
            return preferred
        for candidate in range(47000, 49000):
            if candidate not in used:
                return candidate
        raise ValueError("no loopback port available")

    used = set(unavailable_ports)
    runtime_port = pick(requested_runtime_port, used)
    used.add(runtime_port)
    conflict_port = pick(requested_conflict_port, used)
    return runtime_port, conflict_port


def _rewrite_isolated_launcher_backend(original: dict[str, object], runtime_port: int) -> dict[str, object]:
    rewritten = json.loads(json.dumps(original))
    backend = rewritten["backend"]
    assert isinstance(backend, dict)
    backend["port"] = runtime_port
    return rewritten


def _rewrite_launcher_manifest_entry(manifest: dict[str, object], launcher_text: str) -> dict[str, object]:
    rewritten = json.loads(json.dumps(manifest))
    entries = rewritten["entries"]
    assert isinstance(entries, list)
    launcher_bytes = launcher_text.encode("utf-8")
    launcher_hash = hashlib.sha256(launcher_bytes).hexdigest()
    for entry in entries:
        if entry["path"] == "launcher.json":
            entry["size"] = len(launcher_bytes)
            entry["sha256"] = launcher_hash
            return rewritten
    raise ValueError("launcher.json manifest entry is missing")


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


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, '""'),
        ("", '""'),
        (r"C:\portable\python.exe", r"C:\portable\python.exe"),
        (r"C:\release path\python.exe", r'"C:\release path\python.exe"'),
        (r"C:\中文 路径\python.exe", r'"C:\中文 路径\python.exe"'),
        (r'C:\path with space\\', r'"C:\path with space\\\\"'),
        ('{"message":"hello world"}', r'"{\"message\":\"hello world\"}"'),
        ('a"b', r'"a\"b"'),
    ],
)
def test_windows_process_argument_quoting_vectors(value: str | None, expected: str) -> None:
    assert _quote_windows_process_argument(value) == expected


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"launcher_started": False, "launcher_exited": False, "backend_pid_known": False, "backend_alive": False, "listening_pids": [], "session_pids": [], "http_status": None}, "LAUNCHER_NOT_STARTED"),
        ({"launcher_started": True, "launcher_exited": True, "backend_pid_known": False, "backend_alive": False, "listening_pids": [], "session_pids": [], "http_status": None}, "LAUNCHER_EXITED_EARLY"),
        ({"launcher_started": True, "launcher_exited": False, "backend_pid_known": False, "backend_alive": False, "listening_pids": [], "session_pids": [], "http_status": None}, "BACKEND_NOT_CREATED"),
        ({"launcher_started": True, "launcher_exited": False, "backend_pid_known": True, "backend_alive": False, "listening_pids": [], "session_pids": [], "http_status": None}, "BACKEND_EXITED_EARLY"),
        ({"launcher_started": True, "launcher_exited": False, "backend_pid_known": True, "backend_alive": True, "listening_pids": [9], "session_pids": [4], "http_status": None}, "PORT_OWNED_BY_OTHER_PROCESS"),
        ({"launcher_started": True, "launcher_exited": False, "backend_pid_known": True, "backend_alive": True, "listening_pids": [4], "session_pids": [4], "http_status": 503}, "HEALTH_HTTP_ERROR"),
        ({"launcher_started": True, "launcher_exited": False, "backend_pid_known": True, "backend_alive": True, "listening_pids": [4], "session_pids": [4], "http_status": None}, "BACKEND_HEALTH_TIMEOUT"),
    ],
)
def test_launcher_health_failure_classification(kwargs: dict[str, object], expected: str) -> None:
    assert _classify_health_failure(**kwargs) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({
            "executable_path": r"C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.1-x64\ChatbotLauncher.exe",
            "command_line": r'"C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.1-x64\ChatbotLauncher.exe"',
            "path_readable": True,
            "creation_time_matches": False,
            "launcher_state_matches": False,
        }, True),
        ({
            "executable_path": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            "command_line": r'powershell -NoProfile -File C:\Users\33031\Desktop\bot\scripts\start-local.ps1',
            "path_readable": True,
            "creation_time_matches": False,
            "launcher_state_matches": False,
        }, False),
        ({
            "executable_path": None,
            "command_line": r'python.exe C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.1-x64\server\app\packaging\server\entrypoint.py',
            "path_readable": False,
            "creation_time_matches": True,
            "launcher_state_matches": False,
        }, False),
        ({
            "executable_path": r"C:\Users\33031\Desktop\bot\build\release\Chatbot-Trial-0.1.1-x64\server\runtime\python\python.exe",
            "command_line": r'python.exe entrypoint.py',
            "path_readable": True,
            "creation_time_matches": False,
            "launcher_state_matches": True,
        }, True),
        ({
            "executable_path": r"C:\Users\33031\AppData\Local\Programs\Python\Python311\python.exe",
            "command_line": r'python.exe -m http.server',
            "path_readable": True,
            "creation_time_matches": False,
            "launcher_state_matches": False,
        }, False),
    ],
)
def test_residual_cleanup_candidate_requires_identity_proof(kwargs: dict[str, object], expected: bool) -> None:
    assert _is_safe_residual_cleanup_candidate(**kwargs) is expected  # type: ignore[arg-type]


def test_launcher_state_backend_schema_requires_current_fields() -> None:
    pid, created_at, executable_path, session_id = _parse_launcher_state_backend(
        {
            "backend": {
                "pid": 4321,
                "processCreateTimeUtc": "2026-07-10T00:00:00Z",
                "executablePath": r"C:\release\server\runtime\python\python.exe",
                "sessionId": "session-123",
            }
        }
    )
    assert pid == 4321
    assert created_at == "2026-07-10T00:00:00Z"
    assert executable_path.endswith("python.exe")
    assert session_id == "session-123"


@pytest.mark.parametrize(
    "state",
    [
        {},
        {"backend": None},
        {"backend": {"pid": "4321"}},
        {"backend": {"pid": 4321, "processCreateTimeUtc": "", "executablePath": "python.exe", "sessionId": "x"}},
        {"backend": {"pid": 4321, "processCreateTimeUtc": "2026-07-10T00:00:00Z", "executablePath": "", "sessionId": "x"}},
    ],
)
def test_launcher_state_backend_schema_rejects_legacy_or_partial_payloads(state: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="LAUNCHER_STATE_SCHEMA_INVALID"):
        _parse_launcher_state_backend(state)


@pytest.mark.parametrize(
    ("previous_stage_status", "expected"),
    [("PASS", True), ("FAIL", False), ("UNVERIFIED", False)],
)
def test_port_conflict_stage_only_runs_after_successful_launcher_runtime(previous_stage_status: str, expected: bool) -> None:
    assert _should_run_port_conflict(previous_stage_status) is expected


def test_runtime_verification_ports_are_distinct_and_loopback_only() -> None:
    runtime_port, conflict_port = _select_runtime_ports(0, 0, {47000, 47001})
    assert runtime_port != conflict_port
    assert runtime_port not in {47000, 47001}
    assert conflict_port not in {47000, 47001}
    requested_runtime, requested_conflict = _select_runtime_ports(48081, 48082, set())
    assert (requested_runtime, requested_conflict) == (48081, 48082)
    with pytest.raises(ValueError):
        _select_runtime_ports(48081, 48081, set())


def test_isolated_launcher_config_only_overrides_backend_port() -> None:
    original = {
        "backend": {
            "host": "127.0.0.1",
            "port": 5302,
            "healthPath": "/healthz",
            "runtimeStatusPath": "/api/v1/desktop-automation/runtime/status",
            "startupTimeoutSeconds": 90,
        },
        "ui": {"autoOpenBrowser": False},
    }
    rewritten = _rewrite_isolated_launcher_backend(original, runtime_port=48123)
    assert original["backend"]["port"] == 5302
    assert rewritten["backend"]["port"] == 48123
    assert rewritten["backend"]["host"] == "127.0.0.1"
    assert rewritten["backend"]["healthPath"] == original["backend"]["healthPath"]
    assert rewritten["backend"]["runtimeStatusPath"] == original["backend"]["runtimeStatusPath"]
    assert rewritten["ui"] == original["ui"]


def test_isolated_manifest_rewrites_launcher_entry_size_and_hash_only() -> None:
    original = {
        "schemaVersion": 1,
        "entries": [
            {"path": "launcher.json", "size": 220, "sha256": "old", "critical": True},
            {"path": "ChatbotLauncher.exe", "size": 100, "sha256": "keep", "critical": True},
        ],
    }
    launcher_text = json.dumps(
        {
            "schemaVersion": 1,
            "backend": {
                "host": "127.0.0.1",
                "port": 48123,
                "healthPath": "/healthz",
                "runtimeStatusPath": "/api/v1/desktop-automation/runtime/status",
                "startupTimeoutSeconds": 60,
            },
        },
        ensure_ascii=False,
    )
    rewritten = _rewrite_launcher_manifest_entry(original, launcher_text)
    launcher_entry = next(entry for entry in rewritten["entries"] if entry["path"] == "launcher.json")
    assert launcher_entry["size"] == len(launcher_text.encode("utf-8"))
    assert launcher_entry["sha256"] == hashlib.sha256(launcher_text.encode("utf-8")).hexdigest()
    other_entry = next(entry for entry in rewritten["entries"] if entry["path"] == "ChatbotLauncher.exe")
    assert other_entry["sha256"] == "keep"
    assert original["entries"][0]["size"] == 220


def test_task17_scripts_cover_required_release_safety_terms() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")
    for term in [
        "LANGBOT_BROADCAST_SEND_ENABLED",
        "LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS",
        "LANGBOT_RPA_ALLOW_AUTO_SEND",
        "LANGBOT_RPA_FORCE_DISABLE_SEND",
        "PYTHONDONTWRITEBYTECODE",
        "connectors\\runtime",
        "server\\runtime",
        "runtime\\desktop-rpa",
        "port-conflict",
        "no-residual-processes",
        "release-immutable",
        "ConvertTo-ProcessArgument",
        "$psi.Arguments",
        "CHATBOT_LAUNCHER_NONINTERACTIVE",
        "connector-smoke.stdout.log",
        "connector-smoke.stderr.log",
        "process-snapshot-before",
        "process-snapshot-failure",
        "process-snapshot-cleanup-force",
        "Stop-RemainingControlledProcesses",
        "taskkill.exe /PID",
        "Controlled processes remained after cleanup",
        "port-snapshot.json",
        "launcher-state-copy.json",
        "launcher.stdout.log",
        "launcher.stderr.log",
        "backend.pid",
        "backend.processCreateTimeUtc",
        "backend.executablePath",
        "backend.sessionId",
        "LAUNCHER_STATE_SCHEMA_INVALID",
        "BACKEND_HEALTH_TIMEOUT",
        "HEALTH_RESPONSE_INVALID",
        "Test-LauncherPortAvailability",
        "ChatbotTrialVerify",
        "RuntimeTestPort",
        "PortConflictTestPort",
        "SessionRoot",
        "Get-FreeLoopbackPort",
        "Update-IsolatedLauncherConfig",
        "isolated-launcher.json",
        "isolated-manifest.json",
        "launcher.original.json",
        "127.0.0.1",
        "runtime test port",
        "port-conflict test port",
        "tar -tf",
    ]:
        assert term in verify_script
    assert ".ArgumentList" not in verify_script
    for classification in [
        "LAUNCHER_NOT_STARTED", "LAUNCHER_EXITED_EARLY", "BACKEND_NOT_CREATED",
        "BACKEND_EXITED_EARLY", "PORT_NOT_LISTENING", "PORT_OWNED_BY_OTHER_PROCESS",
        "HEALTH_HTTP_ERROR", "HEALTH_RESPONSE_INVALID", "BACKEND_HEALTH_TIMEOUT",
    ]:
        assert classification in verify_script
    assert "finally" in verify_script and "verify-trial-release-result.json" in verify_script
    for term in ["UpgradeSetupPath", "RUNTIME_STATUS_WAIT", "VERIFY_NO_RESIDUE", "Shortcut", "KeepWorkDirectory", "SkipUpgrade", "SkipUninstall", "Missing Start Menu shortcut", "@(Get-ShortcutEvidence", "@(Wait-ForControlledProcessesExit"]:
        assert term in install_script


def test_verify_script_avoids_reserved_home_variable_assignment() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")
    assert "$home =" not in verify_script.lower()
    assert "$homeResponse =" in verify_script
    assert "$pid =" not in install_script.lower()


def test_verifier_uses_the_isolated_launcher_startup_deadline() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")

    assert "$launcherStartupTimeoutSeconds = [int]$config.backend.startupTimeoutSeconds" in verify_script
    assert "Wait-Http $healthUri $launcherStartupTimeoutSeconds" in verify_script


def test_direct_backend_verifier_waits_through_initializing_runtime_states() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")

    assert 'function Wait-CoreRuntimeStatus' in verify_script
    assert "$status.state -in @('CORE_READY', 'READY', 'DEGRADED')" in verify_script
    assert "$status.state -eq 'FAILED'" in verify_script
    assert 'Wait-CoreRuntimeStatus "http://127.0.0.1:$port/api/v1/system/runtime/status" $StartupTimeoutSeconds' in verify_script


def test_install_script_waits_for_a_core_usable_runtime_state() -> None:
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")
    assert '$status.state -notin @("CORE_READY", "READY", "DEGRADED")' in install_script
    assert '$status.state -eq "FAILED"' in install_script


def test_install_script_honors_the_installed_launcher_startup_deadline() -> None:
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")

    assert "$configured = [int]$Config.backend.startupTimeoutSeconds" in install_script
    assert "Get-InstalledStartupTimeoutSeconds -Config $config" in install_script
    assert "Wait-ForHttpReady -Uri $healthUri -TimeoutSeconds $startupTimeoutSeconds" in install_script
    assert "Wait-Until -TimeoutSeconds $startupTimeoutSeconds" in install_script


def test_install_script_verifies_onboarding_api_endpoints() -> None:
    install_script = INSTALL_SCRIPT.read_text(encoding="utf-8-sig")

    for term in [
        "Stage-OnboardingApi",
        "/readyz",
        "/api/v1/platform/adapters",
        "/api/v1/system/wizard/progress",
        "/api/v1/system/wizard/completed",
        "ONBOARDING_API",
    ]:
        assert term in install_script


def test_verify_script_validates_zip_sha256_sidecar() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")
    assert "$zipSha256Path = $zipFull + '.sha256'" in verify_script
    assert "ZIP checksum sidecar is missing" in verify_script
    assert "ZIP checksum mismatch" in verify_script


def test_verify_script_smokes_final_packaged_server_and_lark_sdk() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")

    for term in [
        "Test-PackagedServerImports",
        "Test-PackagedBackendBoot",
        "server\\runtime\\python\\python.exe",
        "server\\app\\packaging\\server\\entrypoint.py",
        "lark_oapi.api.corehr.v2",
        "lark_oapi.api.core.hr",
        "backend-shutdown.json",
        "/api/v1/system/runtime/status",
    ]:
        assert term in verify_script


def test_verify_script_cleans_packaged_backend_child_processes() -> None:
    verify_script = VERIFY_SCRIPT.read_text(encoding="utf-8-sig")

    for term in [
        "Stop-PackagedBackendChildren",
        "packaged backend child process remained after shutdown",
        "taskkill.exe /PID",
    ]:
        assert term in verify_script
