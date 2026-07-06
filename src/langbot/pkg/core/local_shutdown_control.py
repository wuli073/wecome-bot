from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path


class LocalShutdownControlWatcher:
    def __init__(self, *, app, repo_root: Path, session_id: str, request_path: str) -> None:
        self.app = app
        self.repo_root = Path(repo_root).resolve()
        self.session_id = session_id
        self.request_path = request_path

    def validate_control_path(self) -> Path:
        control_root = (self.repo_root / '.tmp' / 'local-stack' / 'control').resolve()
        request_path = Path(self.request_path).expanduser().resolve()
        request_path.relative_to(control_root)
        return request_path

    def consume_shutdown_request(self) -> bool:
        try:
            request_path = self.validate_control_path()
        except Exception:
            return False

        if not request_path.exists():
            return False

        try:
            payload = json.loads(request_path.read_text(encoding='utf-8'))
        except Exception:
            request_path.unlink(missing_ok=True)
            return False

        if payload.get('sessionId') != self.session_id:
            return False
        if payload.get('action') != 'shutdown':
            request_path.unlink(missing_ok=True)
            return False

        reason = str(payload.get('reason') or 'control-request')
        request_path.unlink(missing_ok=True)
        self.app.request_shutdown(f'control-file:{reason}')
        return True

    async def watch(self) -> None:
        while not self.app.shutdown_requested_event.is_set():
            self.consume_shutdown_request()
            await asyncio.sleep(0.5)


def build_local_shutdown_watcher_from_env(*, app, repo_root: Path | None):
    if repo_root is None:
        return None
    session_id = os.environ.get('LANGBOT_LOCAL_STACK_SESSION_ID', '').strip()
    request_path = os.environ.get('LANGBOT_LOCAL_SHUTDOWN_REQUEST_PATH', '').strip()
    if not session_id or not request_path:
        return None

    watcher = LocalShutdownControlWatcher(
        app=app,
        repo_root=repo_root,
        session_id=session_id,
        request_path=request_path,
    )
    try:
        watcher.validate_control_path()
    except Exception:
        if getattr(app, 'logger', None) is not None:
            app.logger.warning('Invalid local shutdown control path; watcher disabled.')
        return None
    return watcher
