from __future__ import annotations

import importlib.util
import json
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

        report = scan_module.scan_release_tree(bundle_root=bundle_root, allowlist_path=allowlist_path)

        finding_types = {finding["type"] for finding in report["findings"]}
        assert "build_machine_path" in finding_types
        assert "desktop_backup_path" in finding_types
        assert "forbidden_file" in finding_types

        rendered = json.dumps(report, ensure_ascii=False)
        assert "C:\\Users\\33031\\Desktop\\bot\\secret.txt" not in rendered
        assert "C:\\Users\\33031\\Desktop\\WeChat Files\\session\\backup.db" not in rendered
