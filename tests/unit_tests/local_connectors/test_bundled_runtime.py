from __future__ import annotations

import os
from pathlib import Path

import pytest


def test_resolve_wechat_decrypt_root_prefers_source_vendor(monkeypatch):
    from langbot.pkg.local_connectors import bundled_runtime

    source_root = Path(r"C:\repo\bot")
    monkeypatch.delenv("WECOME_WECHAT_DECRYPT_DIR", raising=False)
    monkeypatch.setattr(bundled_runtime, "_find_source_root", lambda: source_root)
    monkeypatch.setattr(
        bundled_runtime,
        "_packaged_runtime_candidates",
        lambda: [Path(r"C:\missing\vendor\wechat_decrypt")],
    )
    monkeypatch.setattr(Path, "exists", lambda self: self == source_root / "vendor" / "wechat_decrypt")

    resolved = bundled_runtime.resolve_wechat_decrypt_root()

    assert resolved == (source_root / "vendor" / "wechat_decrypt").resolve()


def test_resolve_wechat_decrypt_root_allows_explicit_override(monkeypatch):
    from langbot.pkg.local_connectors import bundled_runtime

    override = Path(r"C:\dev\wechat vendored")
    monkeypatch.setenv("WECOME_WECHAT_DECRYPT_DIR", str(override))
    monkeypatch.setattr(bundled_runtime, "_find_source_root", lambda: None)
    monkeypatch.setattr(bundled_runtime, "_packaged_runtime_candidates", lambda: [])
    monkeypatch.setattr(Path, "exists", lambda self: self == override)

    resolved = bundled_runtime.resolve_wechat_decrypt_root()

    assert resolved == override.resolve()


def test_resolve_wechat_decrypt_entrypoint_returns_absolute_path(monkeypatch):
    from langbot.pkg.local_connectors import bundled_runtime

    vendor_root = Path(r"C:\repo\bot\vendor\wechat_decrypt")
    monkeypatch.setattr(bundled_runtime, "resolve_wechat_decrypt_root", lambda: vendor_root)
    monkeypatch.setattr(Path, "exists", lambda self: self == vendor_root / "mcp_http_server.py")

    entrypoint = bundled_runtime.resolve_wechat_decrypt_entrypoint("mcp_http_server.py")

    assert entrypoint == (vendor_root / "mcp_http_server.py").resolve()


def test_resolve_wechat_decrypt_root_raises_clear_error_when_missing(monkeypatch):
    from langbot.pkg.local_connectors import bundled_runtime

    monkeypatch.delenv("WECOME_WECHAT_DECRYPT_DIR", raising=False)
    monkeypatch.setattr(bundled_runtime, "_find_source_root", lambda: None)
    monkeypatch.setattr(bundled_runtime, "_packaged_runtime_candidates", lambda: [])
    monkeypatch.setattr(Path, "exists", lambda self: False)

    with pytest.raises(FileNotFoundError, match="vendor/wechat_decrypt"):
        bundled_runtime.resolve_wechat_decrypt_root()
