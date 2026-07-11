from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


def _load_script_module(module_name: str, script_name: str):
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "packaging" / "build" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _temp_root() -> tempfile.TemporaryDirectory[str]:
    repo_root = Path(__file__).resolve().parents[3]
    build_root = repo_root / "build" / "pytest-temp"
    build_root.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(dir=build_root)


def _run_powershell(command: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        cwd=cwd or Path(__file__).resolve().parents[3],
        text=True,
        capture_output=True,
        check=True,
    )


def _load_build_script_without_entrypoint() -> str:
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "build-trial-release.ps1"
    script_text = script_path.read_text(encoding="utf-8")
    marker = "$repoRoot = Resolve-BuildPath -BasePath $PSScriptRoot -Path '..'"
    assert marker in script_text
    return script_text.split(marker, maxsplit=1)[0]


def test_manifest_builder_marks_critical_and_non_critical_entries() -> None:
    manifest_module = _load_script_module("trial_manifest", "manifest.py")

    with _temp_root() as temp_root:
        tmp_path = Path(temp_root)
        bundle_root = tmp_path / "Chatbot-Trial-0.1.0-x64"
        (bundle_root / "server" / "runtime").mkdir(parents=True)
        (bundle_root / "server" / "runtime" / "python.exe").write_text("python", encoding="utf-8")
        (bundle_root / "resources" / "web" / "dist").mkdir(parents=True)
        (bundle_root / "resources" / "web" / "dist" / "index.html").write_text("<html></html>", encoding="utf-8")
        (bundle_root / "logs").mkdir(parents=True)
        (bundle_root / "logs" / "readme.txt").write_text("log directory placeholder", encoding="utf-8")
        (bundle_root / "ChatbotLauncher.exe").write_text("launcher", encoding="utf-8")

        manifest = manifest_module.build_manifest(bundle_root=bundle_root, version="0.1.0")

        assert manifest["product"] == "Chatbot Trial"
        assert manifest["architecture"] == "x64"
        entries = {entry["path"]: entry for entry in manifest["entries"]}
        assert entries["ChatbotLauncher.exe"]["critical"] is True
        assert entries["resources/web/dist/index.html"]["critical"] is True
        assert entries["logs/readme.txt"]["critical"] is False
        assert len(entries["ChatbotLauncher.exe"]["sha256"]) == 64


def test_sensitive_scan_detects_leaks_and_redacts_report() -> None:
    scan_module = _load_script_module("trial_sensitive_scan", "sensitive-scan.py")

    with _temp_root() as temp_root:
        tmp_path = Path(temp_root)
        bundle_root = tmp_path / "Chatbot-Trial-0.1.0-x64"
        (bundle_root / "resources").mkdir(parents=True)
        leak_text = (
            "developer=C:\\Users\\33031\\Desktop\\bot\\secret.txt\n"
            "backup=C:\\Users\\33031\\Desktop\\WeChat Files\\session\\backup.db\n"
        )
        (bundle_root / "resources" / "notes.txt").write_text(leak_text, encoding="utf-8")
        (bundle_root / "data").mkdir(parents=True)
        (bundle_root / "data" / "runtime.db").write_text("sqlite", encoding="utf-8")
        (bundle_root / "logs").mkdir(parents=True)
        (bundle_root / "logs" / "app.log").write_text("log", encoding="utf-8")

        allowlist_path = tmp_path / "allowlist.json"
        allowlist_path.write_text(
            json.dumps({"pathContains": [], "contentContains": []}, ensure_ascii=False),
            encoding="utf-8",
        )

        report = scan_module.scan_release_tree(
            bundle_root=bundle_root,
            allowlist_path=allowlist_path,
            blocked_literals=[r"C:\Users\33031\Desktop\bot", r"C:\Users\33031\Desktop\WeChat Files"],
        )

        finding_types = {finding["type"] for finding in report["findings"]}
        assert "blocked_literal" in finding_types
        assert "forbidden_file" in finding_types

        rendered = json.dumps(report, ensure_ascii=False)
        assert "C:\\Users\\33031\\Desktop\\bot\\secret.txt" not in rendered
        assert "C:\\Users\\33031\\Desktop\\WeChat Files\\session\\backup.db" not in rendered


def test_sanitize_bundle_removes_bytecode_and_redacts_blocked_literals() -> None:
    sanitize_module = _load_script_module("trial_sanitize_bundle", "sanitize-bundle.py")

    with _temp_root() as temp_root:
        tmp_path = Path(temp_root)
        bundle_root = tmp_path / "Chatbot-Trial-0.1.1-x64"
        bytecode_dir = bundle_root / "server" / "app" / "__pycache__"
        bytecode_dir.mkdir(parents=True)
        (bytecode_dir / "module.cpython-311.pyc").write_bytes(b"pyc")
        text_file = bundle_root / "server" / "runtime" / "python" / "Lib" / "site-packages" / "numpy" / "__config__.py"
        text_file.parent.mkdir(parents=True)
        text_file.write_text(r"C:\Users\runneradmin\AppData\Local\Temp\build-env-abc\python.exe", encoding="utf-8")
        record = bundle_root / "server" / "runtime" / "python" / "Lib" / "site-packages" / "demo-1.0.0.dist-info" / "RECORD"
        record.parent.mkdir(parents=True)
        record.write_text("record", encoding="utf-8")

        report = sanitize_module.sanitize_bundle(bundle_root=bundle_root)

        assert not (bytecode_dir / "module.cpython-311.pyc").exists()
        assert not bytecode_dir.exists()
        assert not record.exists()
        assert "runneradmin" not in text_file.read_text(encoding="utf-8")
        assert report["remainingBytecodeFiles"] == []
        assert report["remainingPycacheDirectories"] == []


def test_build_context_uses_trial_work_staging_root() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "packaging" / "build" / "BuildContext.psm1"
    output_root = repo_root / "build" / "release-test-out"
    output_root.mkdir(parents=True, exist_ok=True)
    command = (
        f"Import-Module '{module_path}' -Force -WarningAction SilentlyContinue; "
        f"$ctx = New-BuildContext -RepoRoot '{repo_root}' -OutputRoot '{output_root}' -Version '0.1.1' "
        "-Offline:$false -SkipTests:$true -KeepWorkDirectory:$true -PortableOnly:$true -VcRedistPath '' -AuditWechatDecryptSource ''; "
        "$ctx | ConvertTo-Json -Depth 5"
    )
    result = _run_powershell(command)
    payload = json.loads(result.stdout)

    assert Path(payload["WorkDirectory"]).parts[-3:] == ("build", ".trial-work", Path(payload["WorkDirectory"]).name)
    assert Path(payload["PortableRoot"]).parts[-5:-1] == ("build", ".trial-work", Path(payload["WorkDirectory"]).name, "portable")
    assert Path(payload["PortablePublishRoot"]).parent == output_root.resolve()
    assert Path(payload["PortableZipStagingPath"]).name.endswith(payload["SessionId"])
    assert Path(payload["PortableZipPublishPath"]).parent == output_root.resolve()


def test_publish_staged_directory_swaps_previous_release_atomically() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "packaging" / "build" / "BuildContext.psm1"

    with _temp_root() as temp_root:
        tmp_path = Path(temp_root)
        output_root = tmp_path / "release"
        output_root.mkdir()
        portable_root = output_root / "Chatbot-Trial-0.1.1-x64"
        portable_root.mkdir()
        (portable_root / "marker.txt").write_text("old", encoding="utf-8")
        staging_root = tmp_path / "staging" / "Chatbot-Trial-0.1.1-x64"
        staging_root.mkdir(parents=True)
        (staging_root / "marker.txt").write_text("new", encoding="utf-8")

        command = (
            f"Import-Module '{module_path}' -Force -WarningAction SilentlyContinue; "
            f"$ctx = New-BuildContext -RepoRoot '{repo_root}' -OutputRoot '{output_root}' -Version '0.1.1' "
            "-Offline:$false -SkipTests:$true -KeepWorkDirectory:$true -PortableOnly:$true -VcRedistPath '' -AuditWechatDecryptSource ''; "
            f"Publish-StagedDirectory -Context $ctx -StagingPath '{staging_root}' -DestinationPath '{portable_root}'; "
            f"Get-ChildItem '{output_root}' -Force | Select-Object Name, PSIsContainer | ConvertTo-Json -Depth 3"
        )
        result = _run_powershell(command)
        parsed = json.loads(result.stdout)
        rows = parsed if isinstance(parsed, list) else [parsed]
        entries = {entry["Name"] for entry in rows}

        assert (portable_root / "marker.txt").read_text(encoding="utf-8") == "new"
        assert not any(name.startswith("Chatbot-Trial-0.1.1-x64.previous-") for name in entries)


def test_portable_artifact_publish_allows_late_setup_publish_after_portable_publish() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "packaging" / "build" / "BuildContext.psm1"
    build_script = _load_build_script_without_entrypoint().replace(
        "Import-Module (Join-Path $PSScriptRoot '..\\packaging\\build\\BuildContext.psm1') -Force",
        f"Import-Module '{module_path}' -Force -WarningAction SilentlyContinue",
    )

    with _temp_root() as temp_root:
        tmp_path = Path(temp_root)
        output_root = tmp_path / "release"
        output_root.mkdir()
        helper_script = tmp_path / "build-functions.ps1"
        helper_script.write_text(build_script, encoding="utf-8")
        result_path = tmp_path / "publish-result.json"

        command = (
            f". '{helper_script}' -Version '0.1.1'; "
            f"$ctx = New-BuildContext -RepoRoot '{repo_root}' -OutputRoot '{output_root}' -Version '0.1.1' "
            "-Offline:$false -SkipTests:$true -KeepWorkDirectory:$true -PortableOnly:$false -VcRedistPath '' -AuditWechatDecryptSource ''; "
            "New-Item -ItemType Directory -Path $ctx.PortableRoot -Force | Out-Null; "
            "Set-Content -LiteralPath (Join-Path $ctx.PortableRoot 'portable.txt') -Value 'portable' -Encoding UTF8; "
            "Invoke-PortableArtifactPublish -Context $ctx; "
            "$ctx.SetupPath = Join-Path $ctx.InstallerStageRoot 'Chatbot-Setup-0.1.1-x64.exe'; "
            "Ensure-Directory -Path $ctx.InstallerStageRoot; "
            "Set-Content -LiteralPath $ctx.SetupPath -Value 'setup' -Encoding UTF8; "
            "Invoke-PortableArtifactPublish -Context $ctx; "
            "$publishedSetupContent = [string](Get-Content -LiteralPath $ctx.SetupPath -Raw); "
            "[ordered]@{ "
            "PortableRoot = $ctx.PortableRoot; "
            "SetupPath = $ctx.SetupPath; "
            "PublishedSetupContent = $publishedSetupContent; "
            "PublishedSetupExists = Test-Path -LiteralPath $ctx.SetupPath -PathType Leaf; "
            f"}} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath '{result_path}' -Encoding UTF8"
        )

        _run_powershell(command)
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))

        assert Path(payload["PortableRoot"]) == (output_root / "Chatbot-Trial-0.1.1-x64").resolve()
        assert Path(payload["SetupPath"]) == (output_root / "Chatbot-Setup-0.1.1-x64.exe").resolve()
        assert payload["PublishedSetupExists"] is True
        assert payload["PublishedSetupContent"].strip() == "setup"


def test_portable_zip_assembly_writes_sha256_sidecar() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "packaging" / "build" / "BuildContext.psm1"
    build_script = _load_build_script_without_entrypoint().replace(
        "Import-Module (Join-Path $PSScriptRoot '..\\packaging\\build\\BuildContext.psm1') -Force",
        f"Import-Module '{module_path}' -Force -WarningAction SilentlyContinue",
    )

    with _temp_root() as temp_root:
        tmp_path = Path(temp_root)
        output_root = tmp_path / "release"
        output_root.mkdir()
        helper_script = tmp_path / "build-functions.ps1"
        helper_script.write_text(build_script, encoding="utf-8")
        result_path = tmp_path / "zip-result.json"

        command = (
            f". '{helper_script}' -Version '0.1.1'; "
            f"$ctx = New-BuildContext -RepoRoot '{repo_root}' -OutputRoot '{output_root}' -Version '0.1.1' "
            "-Offline:$false -SkipTests:$true -KeepWorkDirectory:$true -PortableOnly:$false -VcRedistPath '' -AuditWechatDecryptSource ''; "
            "New-Item -ItemType Directory -Path $ctx.PortableRoot -Force | Out-Null; "
            "Set-Content -LiteralPath (Join-Path $ctx.PortableRoot 'portable.txt') -Value 'portable' -Encoding UTF8; "
            "Invoke-PortableZipAssembly -Context $ctx; "
            "$zipHash = (Get-FileHash -LiteralPath $ctx.PortableZipPath -Algorithm SHA256).Hash.ToLowerInvariant(); "
            "$sidecarText = [string](Get-Content -LiteralPath $ctx.PortableZipSha256Path -Raw); "
            "[ordered]@{ "
            "ZipPath = $ctx.PortableZipPath; "
            "SidecarPath = $ctx.PortableZipSha256Path; "
            "ZipHash = $zipHash; "
            "SidecarText = $sidecarText; "
            f"}} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath '{result_path}' -Encoding UTF8"
        )

        _run_powershell(command)
        payload = json.loads(result_path.read_text(encoding="utf-8-sig"))

        assert Path(payload["SidecarPath"]) == Path(str(payload["ZipPath"]) + ".sha256")
        assert payload["ZipHash"] in payload["SidecarText"]
        assert Path(payload["ZipPath"]).name in payload["SidecarText"]


def test_portable_layout_requires_final_launch_metadata() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    layout = json.loads(
        (repo_root / "packaging" / "build" / "portable-layout.json").read_text(encoding="utf-8")
    )

    required_paths = set(layout["portableRequiredPaths"])
    assert {"ChatbotLauncher.exe", "launcher.json", "manifest.json"} <= required_paths
    assert "manifest.json" not in set(layout["portableForbiddenPaths"])


def test_portable_only_generates_manifest_before_final_layout_check() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    script = (repo_root / "scripts" / "build-trial-release.ps1").read_text(encoding="utf-8")
    build_flow = script.split("try {", maxsplit=1)[1]

    manifest_stage = "Invoke-BuildStage -Context $context -Name 'manifest generation'"
    layout_check_stage = "Invoke-BuildStage -Context $context -Name 'minimal portable layout sanity check'"
    assert manifest_stage in build_flow
    assert build_flow.index(manifest_stage) < build_flow.index(layout_check_stage)


def test_server_lark_sdk_is_pinned_to_verified_complete_release() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    lockfile = (repo_root / "uv.lock").read_text(encoding="utf-8")
    runtime_lock = (repo_root / "packaging" / "server" / "requirements.lock.txt").read_text(
        encoding="utf-8"
    )

    assert '"lark-oapi==1.7.1"' in pyproject
    assert 'name = "lark-oapi"\nversion = "1.7.1"' in lockfile
    assert "lark-oapi==1.7.1" in runtime_lock
