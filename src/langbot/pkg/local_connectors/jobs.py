from __future__ import annotations

import time
import uuid

from . import schemas
from .repository import LocalConnectorRepository


class LocalConnectorJobStore:
    def __init__(self, repository: LocalConnectorRepository) -> None:
        self.repository = repository
        self.jobs: dict[str, dict] = {}

    def create_job(self, connector_id: str) -> dict:
        now = time.time()
        payload = {
            "job_id": str(uuid.uuid4()),
            "connector_id": connector_id,
            "status": schemas.JOB_STATUS_PENDING,
            "stage": schemas.JOB_STAGE_DETECTING,
            "progress": 0,
            "message": "",
            "error_code": None,
            "error_message": None,
            "created_at": now,
            "updated_at": now,
        }
        self.jobs[payload["job_id"]] = payload
        self.repository.save_job(connector_id, payload["job_id"], payload)
        return payload

    def update(self, job: dict, **changes) -> dict:
        job.update(changes)
        job["updated_at"] = time.time()
        self.jobs[job["job_id"]] = job
        self.repository.save_job(job["connector_id"], job["job_id"], job)
        return job

    def get(self, job_id: str) -> dict | None:
        return self.jobs.get(job_id) or self.repository.find_job(job_id)

    def get_latest_for_connector(self, connector_id: str) -> dict | None:
        return self.repository.load_latest_job(connector_id)
