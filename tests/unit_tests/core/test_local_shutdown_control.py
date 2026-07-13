from __future__ import annotations

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

from langbot.pkg.core.local_shutdown_control import (
    LocalShutdownControlWatcher,
    build_local_shutdown_watcher_from_env,
)


pytestmark = pytest.mark.asyncio


async def test_local_shutdown_control_watcher_only_requests_shutdown_for_matching_session(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        repo_root = Path(temp_dir)
        control_dir = repo_root / '.tmp' / 'local-stack' / 'control'
        control_dir.mkdir(parents=True)
        request_path = control_dir / 'shutdown.request.json'
        shutdown_reasons: list[str | None] = []

        app = SimpleNamespace(
            shutdown_requested_event=asyncio.Event(),
            request_shutdown=lambda reason=None: shutdown_reasons.append(reason),
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
        )
        watcher = LocalShutdownControlWatcher(
            app=app,
            repo_root=repo_root,
            session_id='session-a',
            request_path=str(request_path),
        )

        request_path.write_text(
            json.dumps({'sessionId': 'session-b', 'action': 'shutdown', 'reason': 'wrong-session'}),
            encoding='utf-8',
        )
        assert watcher.consume_shutdown_request() is False
        assert shutdown_reasons == []

        request_path.write_text(
            json.dumps({'sessionId': 'session-a', 'action': 'shutdown', 'reason': 'launcher-stop'}),
            encoding='utf-8',
        )
        assert watcher.consume_shutdown_request() is True
        assert shutdown_reasons == ['control-file:launcher-stop']
        assert not request_path.exists()


async def test_build_local_shutdown_watcher_from_env_rejects_path_escape(monkeypatch):
    with TemporaryDirectory(dir=r'C:\Users\33031\Desktop\bot\.tmp-pytest') as temp_dir:
        repo_root = Path(temp_dir)
        escaped_path = repo_root.parent / 'escape.json'
        app = SimpleNamespace(
            logger=SimpleNamespace(warning=lambda *args, **kwargs: None),
            shutdown_requested_event=asyncio.Event(),
            request_shutdown=lambda reason=None: None,
        )

        monkeypatch.setenv('LANGBOT_LOCAL_STACK_SESSION_ID', 'session-a')
        monkeypatch.setenv('LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH', str(escaped_path))

        watcher = build_local_shutdown_watcher_from_env(app=app, repo_root=repo_root)

        assert watcher is None
