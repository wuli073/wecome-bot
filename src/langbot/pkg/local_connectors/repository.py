from __future__ import annotations

import datetime
import json
from pathlib import Path
import secrets
import sqlite3

from ..utils import paths as path_utils


class LocalConnectorRepository:
    def __init__(self) -> None:
        # The source launcher sets CHATBOT_USER_DATA_ROOT for an isolated run.
        # Use the shared resolver in every mode so connector secrets and worker
        # state never leak into a developer's normal LOCALAPPDATA directory.
        self.base_dir = Path(path_utils.get_user_data_root()) / "connectors"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def connector_dir(self, connector_id: str) -> Path:
        path = self.base_dir / connector_id
        for child in ("config", "secrets", "decrypted", "logs", "jobs", "monitor"):
            (path / child).mkdir(parents=True, exist_ok=True)
        return path

    def connector_runtime_dir(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id)

    def state_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "state.json"

    def process_file(self, connector_id: str, role: str = "mcp") -> Path:
        # Legacy process ownership used a shared process.json. The role-scoped
        # files are the only source of truth for current worker ownership.
        return self.connector_dir(connector_id) / f"process.{role}.json"

    def legacy_process_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "process.json"

    def latest_job_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "jobs" / "latest.json"

    def job_file(self, connector_id: str, job_id: str) -> Path:
        return self.connector_dir(connector_id) / "jobs" / f"{job_id}.json"

    def log_file(self, connector_id: str, role: str = "mcp") -> Path:
        if role == "monitor":
            return self.monitor_dir(connector_id) / "monitor.log"
        return self.connector_dir(connector_id) / "logs" / "worker.log"

    def monitor_dir(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "monitor"

    def monitor_state_db_file(self, connector_id: str) -> Path:
        return self.monitor_dir(connector_id) / "monitor_state.db"

    def internal_event_token_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "secrets" / "internal_event_token.txt"

    def save_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load_json(self, path: Path) -> dict | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save_state(self, connector_id: str, payload: dict) -> None:
        self.save_json(self.state_file(connector_id), payload)

    def load_state(self, connector_id: str) -> dict | None:
        return self.load_json(self.state_file(connector_id))

    def save_process(self, connector_id: str, payload: dict | None, role: str = "mcp") -> None:
        path = self.process_file(connector_id, role=role)
        if payload is None:
            if path.exists():
                path.unlink()
            return
        self.save_json(path, payload)

    def load_process(self, connector_id: str, role: str = "mcp") -> dict | None:
        return self.load_json(self.process_file(connector_id, role=role))

    def save_job(self, connector_id: str, job_id: str, payload: dict) -> None:
        self.save_json(self.job_file(connector_id, job_id), payload)
        self.save_json(self.latest_job_file(connector_id), payload)

    def load_job(self, connector_id: str, job_id: str) -> dict | None:
        return self.load_json(self.job_file(connector_id, job_id))

    def load_latest_job(self, connector_id: str) -> dict | None:
        return self.load_json(self.latest_job_file(connector_id))

    def find_job(self, job_id: str) -> dict | None:
        if not self.base_dir.exists():
            return None
        for connector_dir in self.base_dir.iterdir():
            if not connector_dir.is_dir():
                continue
            payload = self.load_json(connector_dir / "jobs" / f"{job_id}.json")
            if payload is not None:
                return payload
        return None

    def read_log_tail(self, connector_id: str, lines: int = 200, role: str = "mcp") -> str:
        log_file = self.log_file(connector_id, role=role)
        if not log_file.exists():
            return ""
        content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])

    def append_log_line(self, connector_id: str, message: str, role: str = "mcp") -> None:
        log_file = self.log_file(connector_id, role=role)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"{message}\n")

    def ensure_internal_event_token(self, connector_id: str) -> str:
        path = self.internal_event_token_file(connector_id)
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        token = secrets.token_urlsafe(32)
        path.write_text(token, encoding="utf-8")
        return token

    def load_internal_event_token(self, connector_id: str) -> str | None:
        path = self.internal_event_token_file(connector_id)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8").strip()

    def read_monitor_runtime_info(self, connector_id: str) -> dict:
        db_file = self.monitor_state_db_file(connector_id)
        if not db_file.exists():
            return {}
        conn = sqlite3.connect(db_file)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            info: dict[str, object] = {}
            if "monitor_state" in tables:
                for key, value in conn.execute("SELECT key, value FROM monitor_state"):
                    info[key] = value
            if "outbox" in tables:
                row = conn.execute(
                    "SELECT COUNT(*) FROM outbox WHERE status != 'delivered'"
                ).fetchone()
                info["outbox_pending"] = int(row[0] or 0)
            return info
        finally:
            conn.close()

    @staticmethod
    def utcnow_iso() -> str:
        return datetime.datetime.utcnow().isoformat()
