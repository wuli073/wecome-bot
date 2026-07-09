from __future__ import annotations


def test_packaged_repository_uses_chatbot_localappdata_root(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    local_app_data = tmp_path / "用户 Space" / "AppData" / "Local"
    monkeypatch.setenv("CHATBOT_PACKAGED", "1")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("CHATBOT_USER_DATA_ROOT", raising=False)

    repository = LocalConnectorRepository()

    assert repository.base_dir == local_app_data / "Chatbot" / "connectors"
    connector_dir = repository.connector_dir("wechat-local")
    assert connector_dir == local_app_data / "Chatbot" / "connectors" / "wechat-local"


def test_packaged_repository_prefers_explicit_user_data_root(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    override_root = tmp_path / "Chatbot Trial Data"
    monkeypatch.setenv("CHATBOT_PACKAGED", "1")
    monkeypatch.setenv("CHATBOT_USER_DATA_ROOT", str(override_root))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Ignored"))

    repository = LocalConnectorRepository()

    assert repository.base_dir == override_root / "connectors"


def test_source_repository_keeps_legacy_wecomebot_root(monkeypatch, tmp_path):
    from langbot.pkg.local_connectors.repository import LocalConnectorRepository

    monkeypatch.delenv("CHATBOT_PACKAGED", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    repository = LocalConnectorRepository()

    assert repository.base_dir == tmp_path / "WecomeBot" / "connectors"
