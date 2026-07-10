from __future__ import annotations

from pathlib import Path


def test_inno_setup_script_covers_trial_requirements() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    installer_path = repo_root / "packaging" / "installer" / "ChatbotTrial.iss"

    content = installer_path.read_text(encoding="utf-8")

    assert "AppId={{2A66BFC0-65B1-4D2F-93A1-9B4A62A0C9C8}" in content
    assert "PrivilegesRequired=lowest" in content
    assert "Name: \"zhHans\"; MessagesFile:" in content
    assert "Name: \"{autodesktop}\\Chatbot Trial\"" in content
    assert "Name: \"{autoprograms}\\Chatbot Trial\"" in content
    assert "CloseApplications=yes" in content
    assert "vc_redist.x64.exe" in content
    assert "ChatbotLauncher.exe" in content
    assert "Remove user data" in content or "删除用户数据" in content
