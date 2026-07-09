from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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
