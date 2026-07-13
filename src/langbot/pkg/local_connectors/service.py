from __future__ import annotations

import asyncio
import hmac
import sys
import time
import uuid

import sqlalchemy

from ..core import app
from ..entity.persistence import mcp as persistence_mcp
from . import schemas, uac_helper
from .connectors.wechat import WechatLocalConnector
from .connectors.wxwork import WxworkLocalConnector
from .jobs import LocalConnectorJobStore
from .models import BUILTIN_CONNECTORS, BuiltinConnectorDefinition
from .process_manager import LocalConnectorProcessManager, PortInUseError, ProcessReadyTimeoutError
from .repository import LocalConnectorRepository
from .runtime_bridge import LocalConnectorRuntimeBridge


class LocalConnectorSetupError(RuntimeError):
    def __init__(self, code: str, message: str, stage: str) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage


class LocalConnectorsService:
    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap
        self.repository = LocalConnectorRepository()
        self.job_store = LocalConnectorJobStore(self.repository)
        self.process_manager = LocalConnectorProcessManager(self.repository)
        self.runtime_bridge = LocalConnectorRuntimeBridge(ap)
        self._definitions = {definition.connector_id: definition for definition in BUILTIN_CONNECTORS}
        self._connectors = {
            "wechat-local": WechatLocalConnector(self._definitions["wechat-local"]),
            "wxwork-local": WxworkLocalConnector(self._definitions["wxwork-local"]),
        }
        self._connector_operation_locks: dict[str, asyncio.Lock] = {}

    def _platform_supported(self) -> bool:
        return sys.platform.startswith("win")

    def _get_connector(self, connector_id: str):
        connector = self._connectors.get(connector_id)
        if connector is None:
            raise ValueError(f"Unknown connector_id: {connector_id}")
        return connector

    def _base_state(self, definition: BuiltinConnectorDefinition, existing: dict | None) -> dict:
        existing = dict(existing or {})
        status = existing.get("status")
        if not status:
            status = (
                schemas.CONNECTOR_STATUS_NOT_CONFIGURED
                if self._platform_supported()
                else schemas.CONNECTOR_STATUS_UNSUPPORTED
            )

        if not self._platform_supported():
            status = schemas.CONNECTOR_STATUS_UNSUPPORTED

        state = {
            "connector_id": definition.connector_id,
            "name": definition.name,
            "builtin": True,
            "locked": True,
            "managed_by": "local_connectors",
            "expected_tool_count": definition.tool_count,
            "status": status,
            "job_status": existing.get("job_status"),
            "job_id": existing.get("job_id"),
            "last_error_code": existing.get("last_error_code"),
            "last_error_message": existing.get("last_error_message"),
            "db_dir": existing.get("db_dir"),
            "keys_file": existing.get("keys_file"),
            "decrypted_dir": existing.get("decrypted_dir"),
            "tool_count": existing.get("tool_count", 0),
            "monitor_enabled": bool(existing.get("monitor_enabled", False)),
            "desktop_automation": dict(existing.get("desktop_automation") or {}),
            "updated_at": existing.get("updated_at", time.time()),
        }
        return state

    def _save_state(self, connector_id: str, **changes) -> dict:
        definition = self._definitions[connector_id]
        state = self._base_state(definition, self.repository.load_state(connector_id))
        state.update(changes)
        state["updated_at"] = time.time()
        self.repository.save_state(connector_id, state)
        return state

    def _get_operation_lock(self, connector_id: str) -> asyncio.Lock:
        lock = self._connector_operation_locks.get(connector_id)
        if lock is None:
            lock = asyncio.Lock()
            self._connector_operation_locks[connector_id] = lock
        return lock

    def _log_connector_stage(
        self,
        stage: str,
        *,
        connector_id: str,
        role: str,
        started_monotonic: float,
        pid: int | None = None,
        port: int | None = None,
    ) -> None:
        logger = getattr(self.ap, "logger", None)
        if logger is None:
            return
        elapsed_ms = int((time.monotonic() - started_monotonic) * 1000)
        logger.info(
            "local_connector_stage "
            f"stage={stage} connector_id={connector_id} role={role} pid={pid} port={port} elapsed_ms={elapsed_ms}"
        )

    async def _ensure_worker_process_ready(self, connector_id: str, *, started_monotonic: float) -> dict:
        connector = self._get_connector(connector_id)
        runtime_dir = str(self.repository.connector_runtime_dir(connector_id))
        self._save_state(
            connector_id,
            status=schemas.JOB_STAGE_STARTING_MCP,
            last_error_code=None,
            last_error_message=None,
        )
        record = await self.process_manager.start(connector, runtime_dir, role=schemas.PROCESS_ROLE_MCP)
        self._log_connector_stage(
            "worker_spawned",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MCP,
            started_monotonic=started_monotonic,
            pid=record.get("controller_pid") or record.get("pid"),
            port=connector.port,
        )
        self._log_connector_stage(
            "tcp_ready",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MCP,
            started_monotonic=started_monotonic,
            pid=record.get("pid"),
            port=connector.port,
        )
        runtime_info = await self.runtime_bridge.wait_for_mcp_protocol_ready(
            self._definitions[connector_id].url,
            expected_tool_names=connector.expected_tool_names,
        )
        self._save_state(
            connector_id,
            status=schemas.CONNECTOR_STATUS_CONNECTED,
            tool_count=runtime_info.get("tool_count", 0),
            last_error_code=None,
            last_error_message=None,
        )
        self._log_connector_stage(
            "mcp_protocol_ready",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MCP,
            started_monotonic=started_monotonic,
            pid=record.get("pid"),
            port=connector.port,
        )
        return runtime_info

    async def _ensure_builtin_session_ready(self, connector_id: str, *, started_monotonic: float) -> dict | None:
        if getattr(self.ap, "tool_mgr", None) is None:
            return None

        connector = self._get_connector(connector_id)
        runtime_info = await self.runtime_bridge.ensure_session_ready(
            connector_id,
            expected_tool_names=connector.expected_tool_names,
        )
        if runtime_info is None:
            return None

        self._save_state(
            connector_id,
            status=schemas.CONNECTOR_STATUS_CONNECTED,
            tool_count=runtime_info.get("tool_count", 0),
            last_error_code=None,
            last_error_message=None,
        )
        self._log_connector_stage(
            "mcp_session_ready",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MCP,
            started_monotonic=started_monotonic,
            pid=self.process_manager.get_process_record(connector_id, role=schemas.PROCESS_ROLE_MCP).get("pid")
            if self.process_manager.get_process_record(connector_id, role=schemas.PROCESS_ROLE_MCP)
            else None,
            port=connector.port,
        )
        return runtime_info

    async def _wait_for_monitor_ready(self, connector_id: str) -> None:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            runtime_info = self.repository.read_monitor_runtime_info(connector_id)
            if runtime_info.get("running_status"):
                return
            await asyncio.sleep(0.2)

    async def _restore_connector(self, connector_id: str, *, allow_session_restore: bool) -> None:
        connector = self._get_connector(connector_id)
        started_monotonic = time.monotonic()
        self._log_connector_stage(
            "restore_started",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MCP,
            started_monotonic=started_monotonic,
            port=connector.port,
        )
        async with self._get_operation_lock(connector_id):
            await self._ensure_worker_process_ready(connector_id, started_monotonic=started_monotonic)
            if allow_session_restore:
                await self._ensure_builtin_session_ready(connector_id, started_monotonic=started_monotonic)

            state = self._base_state(self._definitions[connector_id], self.repository.load_state(connector_id))
            if connector_id == "wxwork-local" and state.get("monitor_enabled"):
                await self.start_monitor(connector_id, enable_on_success=True)

    async def initialize_builtin_mcp_servers(self) -> list[str]:
        result = await self.ap.persistence_mgr.execute_async(sqlalchemy.select(persistence_mcp.MCPServer))
        servers = list(result.all())

        created_or_claimed: list[str] = []
        for definition in BUILTIN_CONNECTORS:
            existing = self._find_existing_server(servers, definition)
            if existing is None:
                payload = {
                    "uuid": str(uuid.uuid4()),
                    **definition.mcp_payload,
                }
                await self.ap.persistence_mgr.execute_async(sqlalchemy.insert(persistence_mcp.MCPServer).values(payload))
                created_or_claimed.append(definition.connector_id)
            else:
                updates = self._build_backfill_values(existing, definition)
                if updates:
                    await self.ap.persistence_mgr.execute_async(
                        sqlalchemy.update(persistence_mcp.MCPServer)
                        .where(persistence_mcp.MCPServer.uuid == existing.uuid)
                        .values(updates)
                    )
            self._save_state(definition.connector_id)

        return created_or_claimed

    def _find_existing_server(
        self,
        servers: list[persistence_mcp.MCPServer],
        definition: BuiltinConnectorDefinition,
    ) -> persistence_mcp.MCPServer | None:
        for server in servers:
            if getattr(server, "connector_id", None) == definition.connector_id:
                return server
        for server in servers:
            extra_args = getattr(server, "extra_args", {}) or {}
            if getattr(server, "name", None) == definition.name:
                return server
            if extra_args.get("url") == definition.url:
                return server
        return None

    def _build_backfill_values(self, server: persistence_mcp.MCPServer, definition: BuiltinConnectorDefinition) -> dict:
        extra_args = dict(getattr(server, "extra_args", {}) or {})
        values = {}
        if getattr(server, "name", None) != definition.name:
            values["name"] = definition.name
        if getattr(server, "mode", None) != "remote":
            values["mode"] = "remote"
        if extra_args.get("url") != definition.url:
            values["extra_args"] = {**extra_args, "url": definition.url}
        if not getattr(server, "builtin", False):
            values["builtin"] = True
        if not getattr(server, "locked", False):
            values["locked"] = True
        if getattr(server, "managed_by", None) != "local_connectors":
            values["managed_by"] = "local_connectors"
        if getattr(server, "connector_id", None) != definition.connector_id:
            values["connector_id"] = definition.connector_id
        return values

    def _configured(self, state: dict) -> bool:
        return bool(state.get("db_dir") or state.get("keys_file") or state.get("decrypted_dir"))

    async def _refresh_runtime_if_enabled(self, connector_id: str, fallback_status: str) -> tuple[str, int]:
        server = await self.ap.mcp_service.get_mcp_server_by_connector_id(connector_id)
        if not server or not server.get("enable"):
            state = self.repository.load_state(connector_id) or {}
            return fallback_status, state.get("tool_count", 0)

        runtime_info = await self.runtime_bridge.enable_and_refresh(connector_id)
        return schemas.CONNECTOR_STATUS_CONNECTED, runtime_info.get("tool_count", 0)

    async def list_connectors(self) -> list[dict]:
        return [await self.get_connector_status(connector_id) for connector_id in self._definitions]

    async def get_connector_status(self, connector_id: str) -> dict:
        connector = self._get_connector(connector_id)
        state = self._base_state(self._definitions[connector_id], self.repository.load_state(connector_id))
        worker_record = self.process_manager.get_process_record(connector_id, role=schemas.PROCESS_ROLE_MCP)
        worker_owned = self.process_manager.is_running(connector_id, role=schemas.PROCESS_ROLE_MCP)
        monitor_record = self.process_manager.get_process_record(connector_id, role=schemas.PROCESS_ROLE_MONITOR)
        monitor_owned = self.process_manager.is_running(connector_id, role=schemas.PROCESS_ROLE_MONITOR)
        monitor_runtime = self.repository.read_monitor_runtime_info(connector_id) if connector_id == "wxwork-local" else {}

        if not self._platform_supported():
            state["status"] = schemas.CONNECTOR_STATUS_UNSUPPORTED
            state["last_error_code"] = "UNSUPPORTED_PLATFORM"
        elif not worker_owned and self._configured(state) and state["status"] in {
            schemas.CONNECTOR_STATUS_CONNECTED,
            schemas.JOB_STAGE_STARTING_MCP,
            schemas.JOB_STAGE_TESTING_MCP,
            schemas.JOB_STAGE_ENABLING_MCP,
        }:
            state["status"] = schemas.CONNECTOR_STATUS_STOPPED

        state["worker"] = {
            "owned": worker_owned,
            "pid": worker_record.get("pid") if worker_owned and worker_record else None,
            "port": connector.port,
            "started_at": worker_record.get("started_at") if worker_owned and worker_record else None,
        }
        monitor_running_status = self._resolve_monitor_running_status(
            enabled=bool(state.get("monitor_enabled")),
            owned=monitor_owned,
            runtime_status=monitor_runtime.get("running_status"),
            last_error=monitor_runtime.get("last_error"),
        )
        state["monitor"] = {
            "enabled": bool(state.get("monitor_enabled")),
            "owned": monitor_owned,
            "pid": monitor_record.get("pid") if monitor_owned and monitor_record else None,
            "started_at": monitor_record.get("started_at") if monitor_owned and monitor_record else None,
            "warmup_completed": self._to_bool(monitor_runtime.get("warmup_completed")),
            "running_status": monitor_running_status,
            "poll_seconds": self._to_int(monitor_runtime.get("poll_seconds")),
            "last_scan_at": monitor_runtime.get("last_scan_at"),
            "last_change_at": monitor_runtime.get("last_change_at"),
            "last_event_at": monitor_runtime.get("last_event_at"),
            "outbox_pending": self._to_int(monitor_runtime.get("outbox_pending"), default=0),
            "last_error": monitor_runtime.get("last_error"),
        }
        return state

    async def detect_connector(self, connector_id: str) -> dict:
        if not self._platform_supported():
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_UNSUPPORTED,
                last_error_code="UNSUPPORTED_PLATFORM",
                last_error_message="Only Windows is supported",
            )

        connector = self._get_connector(connector_id)
        try:
            result = await connector.detect()
        except FileNotFoundError as exc:
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_NOT_CONFIGURED,
                last_error_code="DECRYPT_DIR_NOT_FOUND",
                last_error_message=str(exc),
            )

        if result.get("ok"):
            return self._save_state(
                connector_id,
                status=schemas.JOB_STAGE_DETECTING,
                last_error_code=None,
                last_error_message=None,
                db_dir=result.get("db_dir"),
            )

        status = schemas.CONNECTOR_STATUS_DATA_PATH_NOT_FOUND
        if result.get("error_code") == "CLIENT_NOT_RUNNING":
            status = schemas.CONNECTOR_STATUS_CLIENT_NOT_RUNNING

        return self._save_state(
            connector_id,
            status=status,
            last_error_code=result.get("error_code"),
            last_error_message=result.get("error_message"),
        )

    async def start_setup(self, connector_id: str) -> dict:
        if connector_id not in self._definitions:
            raise ValueError(f"Unknown connector_id: {connector_id}")

        latest = self.job_store.get_latest_for_connector(connector_id)
        if latest and latest.get("status") == schemas.JOB_STATUS_RUNNING:
            return {
                "job_id": latest["job_id"],
                "status": latest["status"],
                "stage": latest.get("stage"),
            }

        job = self.job_store.create_job(connector_id)
        self._save_state(
            connector_id,
            job_status=job["status"],
            job_id=job["job_id"],
            last_error_code=None,
            last_error_message=None,
        )
        asyncio.create_task(self._run_setup_job(job))
        return {"job_id": job["job_id"], "status": job["status"], "stage": job["stage"]}

    async def _run_setup_job(self, job: dict) -> None:
        connector_id = job["connector_id"]
        connector = self._get_connector(connector_id)
        runtime_dir = str(self.repository.connector_runtime_dir(connector_id))

        try:
            if not self._platform_supported():
                raise LocalConnectorSetupError(
                    "UNSUPPORTED_PLATFORM",
                    "Only Windows is supported",
                    schemas.JOB_STAGE_DETECTING,
                )

            self.job_store.update(job, status=schemas.JOB_STATUS_RUNNING, stage=schemas.JOB_STAGE_DETECTING)
            detect_state = await self.detect_connector(connector_id)
            if detect_state["status"] == schemas.CONNECTOR_STATUS_CLIENT_NOT_RUNNING:
                raise LocalConnectorSetupError(
                    detect_state.get("last_error_code") or "CLIENT_NOT_RUNNING",
                    detect_state.get("last_error_message") or "Client is not running",
                    schemas.JOB_STAGE_DETECTING,
                )
            if detect_state["status"] == schemas.CONNECTOR_STATUS_DATA_PATH_NOT_FOUND:
                raise LocalConnectorSetupError(
                    detect_state.get("last_error_code") or "DATA_PATH_NOT_FOUND",
                    detect_state.get("last_error_message") or "Data path not found",
                    schemas.JOB_STAGE_DETECTING,
                )

            self.job_store.update(job, stage=schemas.JOB_STAGE_EXTRACTING_KEY, progress=20)
            self._save_state(connector_id, status=schemas.JOB_STAGE_EXTRACTING_KEY)
            elevated = await uac_helper.run_elevated_extract(
                connector.resolve_python_executable(),
                connector.resolve_entrypoint("connector_cli.py"),
                connector.cli_connector_name,
                runtime_dir,
                self.repository.connector_dir(connector_id) / "jobs" / f"{job['job_id']}-extract.json",
            )
            if not elevated.get("ok"):
                raise LocalConnectorSetupError(
                    elevated.get("error_code") or "KEY_EXTRACTION_FAILED",
                    elevated.get("error_message") or "Key extraction failed",
                    schemas.JOB_STAGE_EXTRACTING_KEY,
                )

            self.job_store.update(job, stage=schemas.JOB_STAGE_DECRYPTING, progress=50)
            self._save_state(
                connector_id,
                status=schemas.JOB_STAGE_DECRYPTING,
                keys_file=elevated.get("keys_file"),
            )
            decrypt_result = await connector.run_cli("decrypt", runtime_dir)
            if not decrypt_result.get("ok"):
                raise LocalConnectorSetupError(
                    decrypt_result.get("error_code") or "DECRYPT_FAILED",
                    decrypt_result.get("error_message") or "Decrypt failed",
                    schemas.JOB_STAGE_DECRYPTING,
                )

            self.job_store.update(job, stage=schemas.JOB_STAGE_STARTING_MCP, progress=70)
            self._save_state(
                connector_id,
                status=schemas.JOB_STAGE_STARTING_MCP,
                decrypted_dir=decrypt_result.get("decrypted_dir"),
            )
            try:
                started_monotonic = time.monotonic()
                await self._ensure_worker_process_ready(connector_id, started_monotonic=started_monotonic)
            except PortInUseError as exc:
                raise LocalConnectorSetupError("PORT_IN_USE", str(exc), schemas.JOB_STAGE_STARTING_MCP) from exc
            except ProcessReadyTimeoutError as exc:
                raise LocalConnectorSetupError(
                    "MCP_TCP_NOT_READY",
                    str(exc),
                    schemas.JOB_STAGE_STARTING_MCP,
                ) from exc
            except TimeoutError as exc:
                raise LocalConnectorSetupError(
                    "MCP_PROTOCOL_NOT_READY",
                    str(exc),
                    schemas.JOB_STAGE_TESTING_MCP,
                ) from exc

            self.job_store.update(job, stage=schemas.JOB_STAGE_TESTING_MCP, progress=80)
            self._save_state(connector_id, status=schemas.JOB_STAGE_TESTING_MCP)

            self.job_store.update(job, stage=schemas.JOB_STAGE_ENABLING_MCP, progress=90)
            self._save_state(connector_id, status=schemas.JOB_STAGE_ENABLING_MCP)
            runtime_info = await self._ensure_builtin_session_ready(
                connector_id,
                started_monotonic=started_monotonic,
            )
            runtime_info = runtime_info or {"tool_count": 0, "tools": []}

            tool_names = {tool["name"] for tool in runtime_info.get("tools", [])}
            if not set(connector.expected_tool_names).issubset(tool_names):
                raise LocalConnectorSetupError(
                    "MCP_HANDSHAKE_FAILED",
                    "Expected MCP tools were not exposed by the worker",
                    schemas.JOB_STAGE_TESTING_MCP,
                )

            self.job_store.update(
                job,
                status=schemas.JOB_STATUS_SUCCEEDED,
                stage=schemas.JOB_STAGE_CONNECTED,
                progress=100,
                message="connected",
            )
            self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_CONNECTED,
                job_status=schemas.JOB_STATUS_SUCCEEDED,
                job_id=job["job_id"],
                tool_count=runtime_info.get("tool_count", 0),
                monitor_enabled=state_monitor_enabled(connector_id, self.repository),
                last_error_code=None,
                last_error_message=None,
            )
            if connector_id == "wxwork-local":
                await self.start_monitor(connector_id, enable_on_success=True)
        except LocalConnectorSetupError as exc:
            self.job_store.update(
                job,
                status=schemas.JOB_STATUS_FAILED,
                stage=exc.stage,
                error_code=exc.code,
                error_message=str(exc),
            )
            self._save_state(
                connector_id,
                status=self._status_for_error(exc.code, exc.stage),
                job_status=schemas.JOB_STATUS_FAILED,
                job_id=job["job_id"],
                last_error_code=exc.code,
                last_error_message=str(exc),
            )
        except Exception as exc:
            self.job_store.update(
                job,
                status=schemas.JOB_STATUS_FAILED,
                stage=job.get("stage", schemas.JOB_STAGE_DETECTING),
                error_code="UNKNOWN_ERROR",
                error_message=str(exc),
            )
            self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_RUNTIME_ERROR,
                job_status=schemas.JOB_STATUS_FAILED,
                job_id=job["job_id"],
                last_error_code="UNKNOWN_ERROR",
                last_error_message=str(exc),
            )

    def _status_for_error(self, error_code: str, stage: str) -> str:
        if error_code == "UNSUPPORTED_PLATFORM":
            return schemas.CONNECTOR_STATUS_UNSUPPORTED
        if error_code == "CLIENT_NOT_RUNNING":
            return schemas.CONNECTOR_STATUS_CLIENT_NOT_RUNNING
        if error_code == "DATA_PATH_NOT_FOUND":
            return schemas.CONNECTOR_STATUS_DATA_PATH_NOT_FOUND
        if error_code == "UAC_CANCELLED":
            return schemas.CONNECTOR_STATUS_PERMISSION_REQUIRED
        if error_code == "PORT_IN_USE":
            return schemas.CONNECTOR_STATUS_PORT_IN_USE
        if error_code in {"MCP_TCP_NOT_READY", "MCP_PROTOCOL_NOT_READY"}:
            return schemas.CONNECTOR_STATUS_RUNTIME_ERROR
        if stage == schemas.JOB_STAGE_DECRYPTING:
            return schemas.CONNECTOR_STATUS_DECRYPT_FAILED
        if stage == schemas.JOB_STAGE_STARTING_MCP:
            return schemas.CONNECTOR_STATUS_START_FAILED
        return schemas.CONNECTOR_STATUS_RUNTIME_ERROR

    async def start_worker(self, connector_id: str) -> dict:
        state = self._base_state(self._definitions[connector_id], self.repository.load_state(connector_id))
        if not self._configured(state):
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_NOT_CONFIGURED,
                last_error_code="NOT_CONFIGURED",
                last_error_message="Run setup before starting the worker",
            )

        try:
            started_monotonic = time.monotonic()
            self._log_connector_stage(
                "restore_started",
                connector_id=connector_id,
                role=schemas.PROCESS_ROLE_MCP,
                started_monotonic=started_monotonic,
                port=self._get_connector(connector_id).port,
            )
            async with self._get_operation_lock(connector_id):
                await self._ensure_worker_process_ready(connector_id, started_monotonic=started_monotonic)
                runtime_info = await self._ensure_builtin_session_ready(
                    connector_id,
                    started_monotonic=started_monotonic,
                )
        except PortInUseError as exc:
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_PORT_IN_USE,
                last_error_code="PORT_IN_USE",
                last_error_message=str(exc),
            )
        except (ProcessReadyTimeoutError, TimeoutError) as exc:
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_RUNTIME_ERROR,
                last_error_code="STARTUP_TIMEOUT",
                last_error_message=str(exc),
            )

        runtime_info = runtime_info or self.repository.load_state(connector_id) or {}
        return self._save_state(
            connector_id,
            status=schemas.CONNECTOR_STATUS_CONNECTED,
            tool_count=runtime_info.get("tool_count", state.get("tool_count", 0)),
            last_error_code=None,
            last_error_message=None,
        )

    async def stop_worker(self, connector_id: str) -> dict:
        connector = self._get_connector(connector_id)
        if connector_id == "wxwork-local":
            await self.stop_monitor(connector_id, disable=True)
        await self.process_manager.stop(connector, role=schemas.PROCESS_ROLE_MCP)
        return self._save_state(connector_id, status=schemas.CONNECTOR_STATUS_STOPPED)

    async def restart_worker(self, connector_id: str) -> dict:
        connector = self._get_connector(connector_id)
        runtime_dir = str(self.repository.connector_runtime_dir(connector_id))
        try:
            await self.process_manager.restart(connector, runtime_dir, role=schemas.PROCESS_ROLE_MCP)
        except PortInUseError as exc:
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_PORT_IN_USE,
                last_error_code="PORT_IN_USE",
                last_error_message=str(exc),
            )
        started_monotonic = time.monotonic()
        await self._ensure_worker_process_ready(connector_id, started_monotonic=started_monotonic)
        runtime_info = await self._ensure_builtin_session_ready(
            connector_id,
            started_monotonic=started_monotonic,
        )
        runtime_info = runtime_info or self.repository.load_state(connector_id) or {}
        return self._save_state(
            connector_id,
            status=schemas.CONNECTOR_STATUS_CONNECTED,
            tool_count=runtime_info.get("tool_count", 0),
        )

    async def refresh_connector(self, connector_id: str) -> dict:
        connector = self._get_connector(connector_id)
        state = self._base_state(self._definitions[connector_id], self.repository.load_state(connector_id))
        if not self._platform_supported():
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_UNSUPPORTED,
                last_error_code="UNSUPPORTED_PLATFORM",
                last_error_message="Only Windows is supported",
            )
        if not self._configured(state):
            return await self.detect_connector(connector_id)

        runtime_dir = str(self.repository.connector_runtime_dir(connector_id))
        self._save_state(connector_id, status=schemas.JOB_STAGE_DECRYPTING)
        decrypt_result = await connector.run_cli("decrypt", runtime_dir)
        if not decrypt_result.get("ok"):
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_DECRYPT_FAILED,
                last_error_code=decrypt_result.get("error_code") or "DECRYPT_FAILED",
                last_error_message=decrypt_result.get("error_message") or "Decrypt failed",
            )

        refreshed_state = self._save_state(
            connector_id,
            status=schemas.CONNECTOR_STATUS_CONNECTED
            if self.process_manager.is_running(connector_id)
            else schemas.CONNECTOR_STATUS_STOPPED,
            decrypted_dir=decrypt_result.get("decrypted_dir"),
            last_error_code=None,
            last_error_message=None,
        )

        server = await self.ap.mcp_service.get_mcp_server_by_connector_id(connector_id)
        if server and server.get("enable"):
            runtime_info = await self.runtime_bridge.enable_and_refresh(connector_id)
            refreshed_state["tool_count"] = runtime_info.get("tool_count", refreshed_state.get("tool_count", 0))
            self.repository.save_state(connector_id, refreshed_state)

        return refreshed_state

    def get_job(self, job_id: str) -> dict | None:
        return self.job_store.get(job_id)

    def get_logs(self, connector_id: str) -> dict:
        self._get_connector(connector_id)
        return {"connector_id": connector_id, "logs": self.repository.read_log_tail(connector_id)}

    def get_internal_event_token(self, connector_id: str) -> str:
        if connector_id != "wxwork-local":
            raise ValueError("Only wxwork-local supports internal events")
        return self.repository.ensure_internal_event_token(connector_id)

    def validate_internal_event_token(self, connector_id: str, token: str) -> bool:
        expected = self.repository.load_internal_event_token(connector_id)
        if not expected or not token:
            return False
        return hmac.compare_digest(expected, token)

    def is_loopback_request(self, remote_addr: str | None) -> bool:
        return remote_addr in {"127.0.0.1", "::1", "::ffff:127.0.0.1"}

    async def get_monitor_status(self, connector_id: str) -> dict:
        if connector_id != "wxwork-local":
            raise ValueError("Monitor is only supported for wxwork-local")
        status = await self.get_connector_status(connector_id)
        return status["monitor"]

    async def start_monitor(self, connector_id: str, enable_on_success: bool = True) -> dict:
        if connector_id != "wxwork-local":
            raise ValueError("Monitor is only supported for wxwork-local")
        connector = self._get_connector(connector_id)
        state = self._base_state(self._definitions[connector_id], self.repository.load_state(connector_id))
        if not self._configured(state):
            return self._save_state(
                connector_id,
                status=schemas.CONNECTOR_STATUS_NOT_CONFIGURED,
                last_error_code="NOT_CONFIGURED",
                last_error_message="Run setup before starting the monitor",
            )
        started_monotonic = time.monotonic()
        self._log_connector_stage(
            "restore_started",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MONITOR,
            started_monotonic=started_monotonic,
        )
        await self._ensure_worker_process_ready(connector_id, started_monotonic=started_monotonic)
        if getattr(self.ap, "tool_mgr", None) is not None:
            await self._ensure_builtin_session_ready(connector_id, started_monotonic=started_monotonic)
        self.repository.ensure_internal_event_token(connector_id)
        runtime_dir = str(self.repository.connector_runtime_dir(connector_id))
        env_overrides = {
            "WECOME_LANGBOT_INTERNAL_EVENT_URL": self._internal_event_url(),
            "WECOME_INTERNAL_EVENT_TOKEN_FILE": str(self.repository.internal_event_token_file(connector_id)),
            "WECOME_MONITOR_STATE_DB": str(self.repository.monitor_state_db_file(connector_id)),
        }
        record = await self.process_manager.start(
            connector,
            runtime_dir,
            role=schemas.PROCESS_ROLE_MONITOR,
            env_overrides=env_overrides,
        )
        self._log_connector_stage(
            "monitor_spawned",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MONITOR,
            started_monotonic=started_monotonic,
            pid=record.get("pid"),
        )
        await self._wait_for_monitor_ready(connector_id)
        self._log_connector_stage(
            "monitor_ready",
            connector_id=connector_id,
            role=schemas.PROCESS_ROLE_MONITOR,
            started_monotonic=started_monotonic,
            pid=record.get("pid"),
        )
        return self._save_state(connector_id, monitor_enabled=enable_on_success)

    async def stop_monitor(self, connector_id: str, disable: bool = True) -> dict:
        if connector_id != "wxwork-local":
            raise ValueError("Monitor is only supported for wxwork-local")
        connector = self._get_connector(connector_id)
        await self.process_manager.stop(connector, role=schemas.PROCESS_ROLE_MONITOR)
        return self._save_state(connector_id, monitor_enabled=not disable)

    async def restart_monitor(self, connector_id: str) -> dict:
        if connector_id != "wxwork-local":
            raise ValueError("Monitor is only supported for wxwork-local")
        connector = self._get_connector(connector_id)
        runtime_dir = str(self.repository.connector_runtime_dir(connector_id))
        env_overrides = {
            "WECOME_LANGBOT_INTERNAL_EVENT_URL": self._internal_event_url(),
            "WECOME_INTERNAL_EVENT_TOKEN_FILE": str(self.repository.internal_event_token_file(connector_id)),
            "WECOME_MONITOR_STATE_DB": str(self.repository.monitor_state_db_file(connector_id)),
        }
        await self.process_manager.restart(
            connector,
            runtime_dir,
            role=schemas.PROCESS_ROLE_MONITOR,
            env_overrides=env_overrides,
        )
        return self._save_state(connector_id, monitor_enabled=True)

    async def restore_configured_connectors(self) -> None:
        if not self._platform_supported() or self.ap.tool_mgr is None:
            allow_session_restore = False
        else:
            allow_session_restore = True

        for connector_id in self._definitions:
            state = self._base_state(self._definitions[connector_id], self.repository.load_state(connector_id))
            if not self._configured(state):
                continue
            try:
                if allow_session_restore:
                    await self.start_worker(connector_id)
                    if connector_id == "wxwork-local" and state.get("monitor_enabled"):
                        await self.start_monitor(connector_id, enable_on_success=True)
                else:
                    started_monotonic = time.monotonic()
                    self._log_connector_stage(
                        "restore_started",
                        connector_id=connector_id,
                        role=schemas.PROCESS_ROLE_MCP,
                        started_monotonic=started_monotonic,
                        port=self._get_connector(connector_id).port,
                    )
                    async with self._get_operation_lock(connector_id):
                        await self._ensure_worker_process_ready(
                            connector_id,
                            started_monotonic=started_monotonic,
                        )
            except Exception as exc:
                self._save_state(
                    connector_id,
                    status=schemas.CONNECTOR_STATUS_RUNTIME_ERROR,
                    last_error_code="RESTORE_FAILED",
                    last_error_message=str(exc),
                )
                logger = getattr(self.ap, "logger", None)
                if logger is not None:
                    logger.warning(f"Failed to restore local connector {connector_id}: {exc}")

    def dispose(self) -> None:
        for connector in self._connectors.values():
            self.process_manager.stop_sync(connector, role=schemas.PROCESS_ROLE_MONITOR)
            self.process_manager.stop_sync(connector, role=schemas.PROCESS_ROLE_MCP)

    def _internal_event_url(self) -> str:
        port = int(self.ap.instance_config.data["api"]["port"])
        return f"http://127.0.0.1:{port}/api/v1/local-connectors/internal/events"

    @staticmethod
    def _to_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"1", "true", "yes"}

    @staticmethod
    def _to_int(value: object, default: int | None = None) -> int | None:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _resolve_monitor_running_status(
        *,
        enabled: bool,
        owned: bool,
        runtime_status: object,
        last_error: object,
    ) -> str:
        normalized_status = str(runtime_status or "").strip().lower()
        if owned:
            return normalized_status or "running"
        if enabled:
            if normalized_status == "error" and str(last_error or "").strip():
                return "error"
            return "starting"
        return "stopped"


def state_monitor_enabled(connector_id: str, repository: LocalConnectorRepository) -> bool:
    state = repository.load_state(connector_id) or {}
    return bool(state.get("monitor_enabled", connector_id == "wxwork-local"))
