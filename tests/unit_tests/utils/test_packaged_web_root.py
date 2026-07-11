from __future__ import annotations

import importlib
import sys
import types
from types import SimpleNamespace

import pytest


def test_packaged_frontend_path_prefers_shared_resources_root(monkeypatch, tmp_path):
    from langbot.pkg.utils import paths

    install_root = tmp_path / "Chatbot Trial"
    dist_root = install_root / "resources" / "web" / "dist"
    dist_root.mkdir(parents=True)
    (dist_root / "index.html").write_text("<html>packaged</html>", encoding="utf-8")

    monkeypatch.setenv("CHATBOT_PACKAGED", "1")
    monkeypatch.setenv("CHATBOT_INSTALL_ROOT", str(install_root))
    monkeypatch.delenv("CHATBOT_WEB_ROOT", raising=False)

    assert paths.get_frontend_path() == str(dist_root.resolve())


@pytest.mark.asyncio
async def test_packaged_http_controller_serves_assets_and_spa_fallback(monkeypatch, tmp_path):
    install_root = tmp_path / "Chatbot Trial"
    dist_root = install_root / "resources" / "web" / "dist"
    assets_root = dist_root / "assets"
    assets_root.mkdir(parents=True)
    (dist_root / "index.html").write_text("<html><body>spa index</body></html>", encoding="utf-8")
    (dist_root / "404.html").write_text("<html><body>missing</body></html>", encoding="utf-8")
    (assets_root / "app.js").write_text("console.log('packaged asset');", encoding="utf-8")

    monkeypatch.setenv("CHATBOT_PACKAGED", "1")
    monkeypatch.setenv("CHATBOT_INSTALL_ROOT", str(install_root))
    monkeypatch.setenv("CHATBOT_WEB_ROOT", str(dist_root))
    core_app_stub = types.ModuleType("langbot.pkg.core.app")
    core_app_stub.Application = object
    previous_core_app_module = sys.modules.get("langbot.pkg.core.app")
    sys.modules["langbot.pkg.core.app"] = core_app_stub
    try:
        group = importlib.import_module("langbot.pkg.api.http.controller.group")
        main_module = importlib.import_module("langbot.pkg.api.http.controller.main")
        monkeypatch.setattr(group, "preregistered_groups", [])

        controller = main_module.HTTPController(SimpleNamespace())
        await controller.register_routes()
        client = controller.quart_app.test_client()

        index_response = await client.get("/")
        asset_response = await client.get("/assets/app.js")
        spa_response = await client.get("/workspace/conversations/123")

        assert index_response.status_code == 200
        assert "spa index" in (await index_response.get_data(as_text=True))
        assert asset_response.status_code == 200
        assert "packaged asset" in (await asset_response.get_data(as_text=True))
        assert spa_response.status_code == 200
        assert "spa index" in (await spa_response.get_data(as_text=True))
    finally:
        if previous_core_app_module is not None:
            sys.modules["langbot.pkg.core.app"] = previous_core_app_module
        else:
            sys.modules.pop("langbot.pkg.core.app", None)
