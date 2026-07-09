from __future__ import annotations

import sys
from pathlib import Path

import pytest


def test_wechat_connector_uses_bundled_entrypoint_and_current_python(monkeypatch):
    from langbot.pkg.local_connectors.connectors.wechat import WechatLocalConnector
    from langbot.pkg.local_connectors.models import BUILTIN_CONNECTORS

    connector = WechatLocalConnector(BUILTIN_CONNECTORS[0])
    vendor_root = Path(r"C:\repo\bot\vendor\wechat_decrypt")
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_root",
        lambda: vendor_root,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_entrypoint",
        lambda name: vendor_root / name,
    )

    command = connector.build_start_command()
    identity = connector.build_command_identity(r"C:\Users\33031\AppData\Local\WecomeBot\connectors\wechat-local")

    assert command == [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        str(vendor_root / "mcp_http_server.py"),
    ]
    assert identity["python_executable"] == str(Path(sys.executable).resolve())
    assert identity["script_path"] == str((vendor_root / "mcp_http_server.py").resolve())


def test_wxwork_connector_appends_runtime_dir_for_monitor(monkeypatch):
    from langbot.pkg.local_connectors.connectors.wxwork import WxworkLocalConnector
    from langbot.pkg.local_connectors.models import BUILTIN_CONNECTORS

    connector = WxworkLocalConnector(BUILTIN_CONNECTORS[1])
    vendor_root = Path(r"C:\repo\bot\vendor\wechat_decrypt")
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_root",
        lambda: vendor_root,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_entrypoint",
        lambda name: vendor_root / name,
    )

    command = connector.build_start_command(
        role="monitor",
        runtime_dir=r"C:\Users\33031\AppData\Local\WecomeBot\connectors\wxwork-local",
    )

    assert command == [
        sys.executable,
        "-u",
        "-X",
        "utf8",
        str(vendor_root / "wxwork_message_monitor.py"),
        "--runtime-dir",
        r"C:\Users\33031\AppData\Local\WecomeBot\connectors\wxwork-local",
    ]


def test_packaged_connector_uses_packaged_python_and_connector_root(monkeypatch):
    from langbot.pkg.local_connectors.connectors.wechat import WechatLocalConnector
    from langbot.pkg.local_connectors.models import BUILTIN_CONNECTORS

    connector = WechatLocalConnector(BUILTIN_CONNECTORS[0])
    packaged_root = Path(r"C:\Program Files\Chatbot Trial\connectors\app\wechat-decrypt")
    packaged_python = Path(r"C:\Program Files\Chatbot Trial\connectors\runtime\python\python.exe")
    runtime_dir = r"C:\Users\测试 用户\AppData\Local\Chatbot\connectors\wechat-local"

    monkeypatch.setenv("CHATBOT_PACKAGED", "1")
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_root",
        lambda: packaged_root,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_entrypoint",
        lambda name: packaged_root / name,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_connector_python_executable",
        lambda: packaged_python,
    )

    command = connector.build_start_command()
    identity = connector.build_command_identity(runtime_dir)

    assert command == [
        str(packaged_python),
        "-u",
        "-X",
        "utf8",
        str(packaged_root / "mcp_http_server.py"),
    ]
    assert identity["python_executable"] == str(packaged_python.resolve())
    assert identity["app_dir"] == str((Path(runtime_dir) / "config").resolve())


def test_packaged_connector_requires_packaged_python(monkeypatch):
    from langbot.pkg.local_connectors.connectors.wechat import WechatLocalConnector
    from langbot.pkg.local_connectors.models import BUILTIN_CONNECTORS

    connector = WechatLocalConnector(BUILTIN_CONNECTORS[0])
    vendor_root = Path(r"C:\Program Files\Chatbot Trial\connectors\app\wechat-decrypt")
    missing_python = Path(r"C:\Program Files\Chatbot Trial\connectors\runtime\python\python.exe")

    monkeypatch.setenv("CHATBOT_PACKAGED", "1")
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_root",
        lambda: vendor_root,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_wechat_decrypt_entrypoint",
        lambda name: vendor_root / name,
    )
    monkeypatch.setattr(
        "langbot.pkg.local_connectors.connectors.base.resolve_connector_python_executable",
        lambda: (_ for _ in ()).throw(FileNotFoundError(str(missing_python))),
    )

    with pytest.raises(FileNotFoundError, match="python.exe"):
        connector.build_start_command()
