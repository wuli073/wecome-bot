from __future__ import annotations

import sys
from pathlib import Path


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
