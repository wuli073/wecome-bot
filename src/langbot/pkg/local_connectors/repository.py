from __future__ import annotations

import json
import os
from pathlib import Path


class LocalConnectorRepository:
    def __init__(self) -> None:
        base_dir = os.environ.get("LOCALAPPDATA", "")
        if base_dir:
            self.base_dir = Path(base_dir) / "WecomeBot" / "connectors"
        else:
            self.base_dir = Path.cwd() / "data" / "local-connectors"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def connector_dir(self, connector_id: str) -> Path:
        path = self.base_dir / connector_id
        for child in ("config", "secrets", "decrypted", "logs", "jobs"):
            (path / child).mkdir(parents=True, exist_ok=True)
        return path

    def connector_runtime_dir(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id)

    def state_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "state.json"

    def process_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "process.json"

    def latest_job_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "jobs" / "latest.json"

    def job_file(self, connector_id: str, job_id: str) -> Path:
        return self.connector_dir(connector_id) / "jobs" / f"{job_id}.json"

    def log_file(self, connector_id: str) -> Path:
        return self.connector_dir(connector_id) / "logs" / "worker.log"

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

    def save_process(self, connector_id: str, payload: dict | None) -> None:
        path = self.process_file(connector_id)
        if payload is None:
            if path.exists():
                path.unlink()
            return
        self.save_json(path, payload)

    def load_process(self, connector_id: str) -> dict | None:
        return self.load_json(self.process_file(connector_id))

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

    def read_log_tail(self, connector_id: str, lines: int = 200) -> str:
        log_file = self.log_file(connector_id)
        if not log_file.exists():
            return ""
        content = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])
