from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _load_module(module_name: str, relative_path: str):
    root = Path(__file__).resolve().parents[3]
    module_path = root / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_packaged_install_deps_raises_without_pip(monkeypatch):
    from langbot.pkg.core.bootutils import deps

    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    with patch('langbot.pkg.core.bootutils.deps.pip.main') as pip_main:
        with pytest.raises(deps.PackagedDependencyError) as exc_info:
            run(deps.install_deps(['requests']))

    assert exc_info.value.code == deps.PACKAGED_DEPENDENCY_MISSING
    assert exc_info.value.deps == ['requests']
    pip_main.assert_not_called()


def test_source_install_deps_keeps_existing_behavior(monkeypatch):
    from langbot.pkg.core.bootutils import deps

    monkeypatch.delenv('CHATBOT_PACKAGED', raising=False)
    with patch('langbot.pkg.core.bootutils.deps.pip.main') as pip_main:
        run(deps.install_deps(['requests']))

    pip_main.assert_called_once_with(['install', 'requests'])


def test_packaged_plugin_requirements_are_skipped(monkeypatch):
    from langbot.pkg.core.bootutils import deps

    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    with patch('langbot.pkg.core.bootutils.deps.pkgmgr.install_requirements') as install_requirements:
        run(deps.precheck_plugin_deps())

    install_requirements.assert_not_called()


def test_packaged_backend_config_forces_loopback_and_packaged_roots(tmp_path):
    entrypoint = _load_module(
        'task7_packaged_entrypoint',
        'packaging/server/entrypoint.py',
    )

    install_root = tmp_path / 'Chatbot'
    local_app_data = tmp_path / 'Local App Data'
    config = entrypoint.build_packaged_backend_config(
        install_root=install_root,
        local_app_data=local_app_data,
        host='0.0.0.0',
        port='5302',
    )

    assert config.host == '127.0.0.1'
    assert config.port == 5302
    assert config.resources_root == install_root / 'resources'
    assert config.user_data_root == local_app_data / 'Chatbot'
    assert config.data_root == local_app_data / 'Chatbot' / 'data'
    assert config.log_root == local_app_data / 'Chatbot' / 'logs'
    assert config.runtime_root == local_app_data / 'Chatbot' / 'runtime'
    assert config.shutdown_request_path == local_app_data / 'Chatbot' / 'runtime' / 'backend-shutdown.json'
    assert config.rpa_runtime_path == install_root / 'runtime' / 'desktop-rpa' / 'LangBot Desktop RPA Runtime.exe'


def test_packaged_environment_verifier_accepts_launcher_driven_roots(tmp_path):
    entrypoint = _load_module(
        'task7_packaged_entrypoint_verify',
        'packaging/server/entrypoint.py',
    )
    verifier = _load_module(
        'task7_packaged_verify_runtime',
        'packaging/server/verify_runtime.py',
    )

    config = entrypoint.build_packaged_backend_config(
        install_root=tmp_path / 'Chatbot',
        local_app_data=tmp_path / 'Users' / 'Alice' / 'AppData' / 'Local',
        port=5311,
    )
    env = entrypoint.build_packaged_environment(config, base_env={})

    verifier.verify_runtime_environment(env)

    assert env['API__HOST'] == '127.0.0.1'
    assert env['API__PORT'] == '5311'
    assert env['CHATBOT_BACKEND_HEALTH_PATH'] == '/healthz'
    assert env['CHATBOT_BACKEND_RUNTIME_STATUS_PATH'] == '/api/v1/desktop-automation/runtime/status'
