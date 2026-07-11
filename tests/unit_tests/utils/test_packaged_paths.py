from __future__ import annotations

from pathlib import Path

import pytest


def reset_paths(paths):
    paths._is_source_install = None
    paths._source_root = None


def test_packaged_roots_use_install_and_localappdata(monkeypatch, tmp_path):
    from langbot.pkg.utils import paths

    reset_paths(paths)
    install = tmp_path / '?? Chatbot'
    local = tmp_path / '?? ??'
    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    monkeypatch.setenv('CHATBOT_INSTALL_ROOT', str(install))
    monkeypatch.setenv('LOCALAPPDATA', str(local))
    monkeypatch.delenv('LANGBOT_DATA_ROOT', raising=False)

    assert Path(paths.get_install_root()) == install.resolve()
    assert Path(paths.get_data_root()) == (local / 'Chatbot').resolve()
    assert Path(paths.get_resources_root()) == (install / 'resources').resolve()


def test_packaged_env_overrides_take_precedence(monkeypatch, tmp_path):
    from langbot.pkg.utils import paths

    reset_paths(paths)
    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    monkeypatch.setenv('CHATBOT_INSTALL_ROOT', str(tmp_path / 'install'))
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setenv('LANGBOT_DATA_ROOT', str(tmp_path / 'data override'))
    monkeypatch.setenv('CHATBOT_WEB_ROOT', str(tmp_path / 'web root'))
    monkeypatch.setenv('CHATBOT_TEMPLATE_ROOT', str(tmp_path / '?? root'))

    assert Path(paths.get_data_root()) == (tmp_path / 'data override').resolve()
    assert Path(paths.get_frontend_path()) == (tmp_path / 'web root').resolve()
    assert Path(paths.get_resource_path('templates/config.yaml')) == (tmp_path / '?? root' / 'config.yaml').resolve()


def test_packaged_missing_localappdata_is_error(monkeypatch):
    from langbot.pkg.utils import paths

    reset_paths(paths)
    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    monkeypatch.delenv('LOCALAPPDATA', raising=False)
    monkeypatch.delenv('LANGBOT_DATA_ROOT', raising=False)
    monkeypatch.delenv('CHATBOT_USER_DATA_ROOT', raising=False)

    with pytest.raises(paths.PackagedPathError, match='LOCALAPPDATA'):
        paths.get_data_root()


def test_packaged_arbitrary_working_directory(monkeypatch, tmp_path):
    from langbot.pkg.utils import paths

    reset_paths(paths)
    cwd = tmp_path / 'other cwd'
    cwd.mkdir()
    install = tmp_path / 'Chatbot Root'
    local = tmp_path / '?? AppData'
    monkeypatch.chdir(cwd)
    monkeypatch.setenv('CHATBOT_PACKAGED', '1')
    monkeypatch.setenv('CHATBOT_INSTALL_ROOT', str(install))
    monkeypatch.setenv('LOCALAPPDATA', str(local))

    assert not str(paths.get_frontend_path()).startswith(str(cwd))
    assert Path(paths.get_frontend_path()) == (install / 'resources' / 'web' / 'dist').resolve()
    assert Path(paths.get_resource_path('src/langbot/pkg/persistence/alembic/versions')) == (
        install / 'resources' / 'migrations' / 'versions'
    ).resolve()
