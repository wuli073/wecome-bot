from __future__ import annotations

import logging
import asyncio
import traceback
import os
import json
import time
import datetime

from ..platform import botmgr as im_mgr
from ..platform.webhook_pusher import WebhookPusher
from ..provider.session import sessionmgr as llm_session_mgr
from ..provider.modelmgr import modelmgr as llm_model_mgr
from ..box import service as box_service_module

from langbot.pkg.provider.tools import toolmgr as llm_tool_mgr
from ..config import manager as config_mgr
from ..command import cmdmgr
from ..plugin import connector as plugin_connector
from ..pipeline import pool
from ..pipeline import controller, pipelinemgr
from ..pipeline import aggregator as message_aggregator
from ..utils import version as version_mgr, proxy as proxy_mgr
from ..persistence import mgr as persistencemgr
from ..api.http.controller import main as http_controller
from ..api.http.service import user as user_service
from ..api.http.service import space as space_service
from ..api.http.service import model as model_service
from ..api.http.service import provider as provider_service
from ..api.http.service import pipeline as pipeline_service
from ..api.http.service import bot as bot_service
from ..api.http.service import knowledge as knowledge_service
from ..api.http.service import mcp as mcp_service
from ..api.http.service import apikey as apikey_service
from ..api.http.service import webhook as webhook_service
from ..api.http.service import monitoring as monitoring_service
from ..api.http.service import skill as skill_service
from ..api.http.service import maintenance as maintenance_service
from ..discover import engine as discover_engine
from ..storage import mgr as storagemgr
from ..utils import logcache
from . import taskmgr
from . import entities as core_entities
from ..rag.knowledge import kbmgr as rag_mgr
from ..rag.service import RAGRuntimeService
from ..vector import mgr as vectordb_mgr
from ..telemetry import telemetry as telemetry_module
from ..survey import manager as survey_module
from ..skill import manager as skill_mgr
from ..local_connectors import service as local_connectors_service
from ..database_mode.events import DatabaseModeEventBus
from ..database_mode import service as database_mode_service
from ..database_mode import processing_service as database_mode_processing_service
from ..desktop_automation import service as desktop_automation_service
from ..broadcast import service as broadcast_service
from .local_shutdown_control import LocalShutdownControlWatcher


class Application:
    """Runtime application object and context"""

    LONG_LIVED_CRITICAL_TASK_NAMES = frozenset(
        {
            'query-controller',
            'http-api-controller',
        }
    )

    event_loop: asyncio.AbstractEventLoop = None

    # asyncio_tasks: list[asyncio.Task] = []
    task_mgr: taskmgr.AsyncTaskManager = None

    discover: discover_engine.ComponentDiscoveryEngine = None

    platform_mgr: im_mgr.PlatformManager = None

    webhook_pusher: WebhookPusher = None

    cmd_mgr: cmdmgr.CommandManager = None

    sess_mgr: llm_session_mgr.SessionManager = None

    model_mgr: llm_model_mgr.ModelManager = None

    rag_mgr: rag_mgr.RAGManager = None
    rag_runtime_service: RAGRuntimeService = None

    # TODO move to pipeline
    tool_mgr: llm_tool_mgr.ToolManager = None
    box_service: box_service_module.BoxService = None

    # ======= Config manager =======

    command_cfg: config_mgr.ConfigManager = None  # deprecated

    pipeline_cfg: config_mgr.ConfigManager = None  # deprecated

    platform_cfg: config_mgr.ConfigManager = None  # deprecated

    provider_cfg: config_mgr.ConfigManager = None  # deprecated

    system_cfg: config_mgr.ConfigManager = None  # deprecated

    instance_config: config_mgr.ConfigManager = None

    instance_id: config_mgr.ConfigManager = None  # used to identify the instance

    # ======= Metadata config manager =======

    sensitive_meta: config_mgr.ConfigManager = None

    pipeline_config_meta_trigger: config_mgr.ConfigManager = None
    pipeline_config_meta_safety: config_mgr.ConfigManager = None
    pipeline_config_meta_ai: config_mgr.ConfigManager = None
    pipeline_config_meta_output: config_mgr.ConfigManager = None

    # =========================

    plugin_connector: plugin_connector.PluginRuntimeConnector = None

    query_pool: pool.QueryPool = None

    msg_aggregator: message_aggregator.MessageAggregator = None

    ctrl: controller.Controller = None

    pipeline_mgr: pipelinemgr.PipelineManager = None

    ver_mgr: version_mgr.VersionManager = None

    proxy_mgr: proxy_mgr.ProxyManager = None

    logger: logging.Logger = None

    persistence_mgr: persistencemgr.PersistenceManager = None

    vector_db_mgr: vectordb_mgr.VectorDBManager = None

    http_ctrl: http_controller.HTTPController = None

    log_cache: logcache.LogCache = None

    storage_mgr: storagemgr.StorageMgr = None

    # ========= HTTP Services =========

    user_service: user_service.UserService = None

    space_service: space_service.SpaceService = None

    llm_model_service: model_service.LLMModelsService = None

    embedding_models_service: model_service.EmbeddingModelsService = None

    rerank_models_service: model_service.RerankModelsService = None

    provider_service: provider_service.ModelProviderService = None

    pipeline_service: pipeline_service.PipelineService = None

    bot_service: bot_service.BotService = None

    knowledge_service: knowledge_service.KnowledgeService = None

    mcp_service: mcp_service.MCPService = None
    local_connectors_service: local_connectors_service.LocalConnectorsService = None

    apikey_service: apikey_service.ApiKeyService = None

    webhook_service: webhook_service.WebhookService = None

    telemetry: telemetry_module.TelemetryManager = None

    survey: survey_module.SurveyManager = None

    monitoring_service: monitoring_service.MonitoringService = None

    database_mode_service: database_mode_service.DatabaseModeService = None
    database_mode_processing_service: database_mode_processing_service.DatabaseModeProcessingService = None
    database_mode_event_bus: DatabaseModeEventBus | None = None
    desktop_automation_service: desktop_automation_service.DesktopAutomationService | None = None
    broadcast_service: broadcast_service.BroadcastService | None = None
    broadcast_execution_worker = None

    skill_service: skill_service.SkillService = None

    skill_mgr: skill_mgr.SkillManager = None

    maintenance_service: maintenance_service.MaintenanceService = None
    local_shutdown_control_watcher: LocalShutdownControlWatcher | None = None

    def __init__(self):
        self.shutdown_requested_event = asyncio.Event()
        self._shutdown_lock = asyncio.Lock()
        self._shutdown_task: asyncio.Task[None] | None = None
        self._critical_failure: BaseException | None = None
        self._shutdown_reason: str | None = None
        self.startup_phase = 'initializing'
        self.startup_error: str | None = None
        self.startup_task: asyncio.Task[None] | None = None
        self._boot_started_at = time.monotonic()

    def set_startup_phase(self, stage: str, *, error: str | None = None) -> None:
        """Record a non-sensitive packaged startup transition."""
        self.startup_phase = stage
        self.startup_error = error
        payload = {
            'timestamp': datetime.datetime.now(datetime.UTC).isoformat(),
            'pid': os.getpid(),
            'sessionId': os.environ.get('CHATBOT_LAUNCH_SESSION_ID', ''),
            'stage': stage,
            'elapsedMs': round((time.monotonic() - self._boot_started_at) * 1000),
        }
        if error:
            payload['error'] = error
        message = f'BOOT_STAGE {json.dumps(payload, ensure_ascii=True, separators=(",", ":"))}'
        if self.logger is not None:
            self.logger.info(message)
        else:
            print(message, flush=True)

    async def initialize(self):
        if self.desktop_automation_service is None:
            return

        desktop_automation_cfg = self.instance_config.data.get('desktop_automation', {})
        if not desktop_automation_cfg.get('enabled', False):
            if self.logger is not None:
                self.logger.info('Desktop runtime disabled.')
            return

        async def prewarm_runtime():
            try:
                await self.desktop_automation_service.ensure_runtime_client()
                if self.logger is not None:
                    self.logger.info('Desktop runtime ready (prewarm).')
            except Exception as exc:
                if self.logger is not None:
                    self.logger.warning(f'Desktop runtime prewarm degraded: {exc}')

        self.task_mgr.create_task(
            prewarm_runtime(),
            name='desktop-runtime-prewarm',
            scopes=[core_entities.LifecycleControlScope.APPLICATION],
        )

    def request_shutdown(self, reason: str | None = None) -> None:
        if reason is not None and self._shutdown_reason is None:
            self._shutdown_reason = reason
        self.shutdown_requested_event.set()

    async def run(self) -> int:
        try:
            critical_task_wrappers: dict[str, taskmgr.TaskWrapper] = {}
            if self.startup_task is not None:
                critical_task_wrappers['http-api-controller'] = self.task_mgr.create_task(
                    self.http_ctrl.run(),
                    name='http-api-controller',
                    scopes=[core_entities.LifecycleControlScope.APPLICATION],
                )
                await self.http_ctrl.wait_until_listening()
                if self.startup_phase != 'ready':
                    self.set_startup_phase('http_server_listening')
                    self.set_startup_phase('health_available')

                shutdown_waiter = asyncio.create_task(self.shutdown_requested_event.wait())
                done, _ = await asyncio.wait(
                    {self.startup_task, shutdown_waiter},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                shutdown_waiter.cancel()
                await asyncio.gather(shutdown_waiter, return_exceptions=True)
                if self.shutdown_requested_event.is_set():
                    self.startup_task.cancel()
                    await asyncio.gather(self.startup_task, return_exceptions=True)
                    await self.shutdown()
                    return 0
                self.startup_task.result()
                await self.initialize()

            await self.plugin_connector.initialize_plugins()

            try:
                await self.platform_mgr.run()
            except Exception as exc:
                self._critical_failure = exc
                self.request_shutdown('critical-task:platform-manager')
                await self.shutdown()
                return 1

            if self.shutdown_requested_event.is_set():
                await self.shutdown()
                return 0

            critical_task_wrappers['query-controller'] = self.task_mgr.create_task(
                self.ctrl.run(),
                name='query-controller',
                scopes=[core_entities.LifecycleControlScope.APPLICATION],
            )
            if 'http-api-controller' not in critical_task_wrappers:
                critical_task_wrappers['http-api-controller'] = self.task_mgr.create_task(
                    self.http_ctrl.run(),
                    name='http-api-controller',
                    scopes=[core_entities.LifecycleControlScope.APPLICATION],
                )
            # Telemetry instance heartbeat (startup + daily); respects
            # space.disable_telemetry via TelemetryManager.send().
            if self.telemetry is not None:
                from ..telemetry import heartbeat as telemetry_heartbeat

                self.task_mgr.create_task(
                    telemetry_heartbeat.heartbeat_loop(self),
                    name='telemetry-heartbeat',
                    scopes=[core_entities.LifecycleControlScope.APPLICATION],
                )

            monitoring_cfg = self.instance_config.data.get('monitoring', {})
            auto_cleanup_cfg = monitoring_cfg.get('auto_cleanup', {})
            if auto_cleanup_cfg.get('enabled', True):
                retention_days = self._get_positive_int_config(
                    auto_cleanup_cfg.get('retention_days', 30),
                    default=30,
                    name='monitoring.auto_cleanup.retention_days',
                )
                delete_batch_size = self._get_positive_int_config(
                    auto_cleanup_cfg.get('delete_batch_size', 1000),
                    default=1000,
                    name='monitoring.auto_cleanup.delete_batch_size',
                )
                check_interval_hours = self._get_positive_float_config(
                    auto_cleanup_cfg.get('check_interval_hours', 1),
                    default=1,
                    name='monitoring.auto_cleanup.check_interval_hours',
                )

                async def monitoring_cleanup_loop():
                    check_interval_seconds = check_interval_hours * 3600
                    while True:
                        try:
                            deleted = await self.monitoring_service.cleanup_expired_records(
                                retention_days,
                                batch_size=delete_batch_size,
                            )
                            total_deleted = sum(deleted.values())
                            if total_deleted > 0:
                                self.logger.info(
                                    f'Monitoring auto-cleanup: deleted {total_deleted} expired records '
                                    f'(retention={retention_days}d): {deleted}'
                                )
                        except Exception as e:
                            self.logger.warning(f'Monitoring auto-cleanup error: {e}')
                        await asyncio.sleep(check_interval_seconds)

                self.task_mgr.create_task(
                    monitoring_cleanup_loop(),
                    name='monitoring-cleanup',
                    scopes=[core_entities.LifecycleControlScope.APPLICATION],
                )

            storage_cleanup_cfg = self.instance_config.data.get('storage', {}).get('cleanup', {})
            if storage_cleanup_cfg.get('enabled', True) and self.maintenance_service is not None:
                check_interval_hours = self._get_positive_float_config(
                    storage_cleanup_cfg.get('check_interval_hours', 1),
                    default=1,
                    name='storage.cleanup.check_interval_hours',
                )

                async def storage_cleanup_loop():
                    check_interval_seconds = check_interval_hours * 3600
                    while True:
                        try:
                            deleted = await self.maintenance_service.cleanup_expired_files()
                            total_deleted = sum(deleted.values())
                            if total_deleted > 0:
                                self.logger.info(f'Storage maintenance: deleted expired files: {deleted}')
                        except Exception as e:
                            self.logger.warning(f'Storage maintenance error: {e}')
                        await asyncio.sleep(check_interval_seconds)

                self.task_mgr.create_task(
                    storage_cleanup_loop(),
                    name='storage-maintenance',
                    scopes=[core_entities.LifecycleControlScope.APPLICATION],
                )

            await self.print_web_access_info()
            shutdown_waiter = asyncio.create_task(
                self.shutdown_requested_event.wait(),
                name='shutdown-requested-waiter',
            )
            try:
                while True:
                    critical_wrappers = self._get_critical_task_wrappers(critical_task_wrappers)
                    if self._handle_completed_critical_tasks(critical_wrappers):
                        break

                    wait_targets = [shutdown_waiter, *(wrapper.task for wrapper in critical_wrappers.values())]
                    if len(wait_targets) == 1:
                        await shutdown_waiter
                        break

                    done, _ = await asyncio.wait(
                        wait_targets,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if self._handle_completed_critical_tasks(critical_wrappers, done):
                        break

                    if shutdown_waiter in done:
                        break
            finally:
                shutdown_waiter.cancel()
                await asyncio.gather(shutdown_waiter, return_exceptions=True)

            await self.shutdown()
            return 1 if self._critical_failure is not None else 0
        except asyncio.CancelledError:
            await self.shutdown()
            return 0
        except Exception as e:
            self.logger.error(f'Application runtime fatal exception: {e}')
            self.logger.debug(f'Traceback: {traceback.format_exc()}')
            await self.shutdown()
            return 1

    def _get_critical_task_wrappers(
        self,
        wrappers: dict[str, taskmgr.TaskWrapper] | None = None,
    ) -> dict[str, taskmgr.TaskWrapper]:
        critical_wrappers: dict[str, taskmgr.TaskWrapper] = {}
        wrapper_iterable = wrappers.values() if wrappers is not None else list(self.task_mgr.tasks)
        for wrapper in wrapper_iterable:
            if wrapper.name not in self.LONG_LIVED_CRITICAL_TASK_NAMES:
                continue
            critical_wrappers[wrapper.name or f'task-{wrapper.id}'] = wrapper
        return critical_wrappers

    def _handle_completed_critical_tasks(
        self,
        critical_wrappers: dict[str, taskmgr.TaskWrapper],
        done_tasks: set[asyncio.Task] | None = None,
    ) -> bool:
        shutdown_requested = self.shutdown_requested_event.is_set()
        for name, wrapper in critical_wrappers.items():
            task = wrapper.task
            if done_tasks is not None and task not in done_tasks and not task.done():
                continue

            failure = self._get_critical_task_failure(
                name,
                task,
                shutdown_requested=shutdown_requested,
            )
            if failure is None:
                continue

            if self._critical_failure is None:
                self._critical_failure = failure
            self.request_shutdown(f'critical-task:{name}')
            return True

        return False

    def _get_critical_task_failure(
        self,
        name: str,
        task: asyncio.Task,
        *,
        shutdown_requested: bool,
    ) -> BaseException | None:
        if not task.done():
            return None
        if shutdown_requested and task.cancelled():
            return None
        if task.cancelled():
            return asyncio.CancelledError()

        task_exception = task.exception()
        if task_exception is not None:
            return task_exception

        return RuntimeError(f'{name} exited unexpectedly')

    async def shutdown(self) -> None:
        async with self._shutdown_lock:
            if self._shutdown_task is None:
                self._shutdown_task = self.event_loop.create_task(
                    self._shutdown_impl(),
                    name='application-shutdown',
                )
            shutdown_task = self._shutdown_task
        await shutdown_task

    async def _shutdown_impl(self) -> None:
        if self.http_ctrl is not None and hasattr(self.http_ctrl, 'request_shutdown'):
            try:
                self.http_ctrl.request_shutdown()
            except Exception as exc:
                if self.logger is not None:
                    self.logger.warning(f'HTTP shutdown request failed: {exc}')

        if self.broadcast_execution_worker is not None:
            try:
                await self.broadcast_execution_worker.stop()
            except Exception as exc:
                if self.logger is not None:
                    self.logger.warning(f'Broadcast worker stop failed: {exc}')

        if self.desktop_automation_service is not None:
            try:
                await self.desktop_automation_service.shutdown()
            except Exception as exc:
                if self.logger is not None:
                    self.logger.warning(f'Desktop automation shutdown failed: {exc}')

        if self.task_mgr is not None:
            try:
                await self.task_mgr.cancel_and_wait_by_scope(
                    core_entities.LifecycleControlScope.APPLICATION,
                    timeout=10,
                )
            except Exception as exc:
                if self.logger is not None:
                    self.logger.warning(f'Application task cancellation failed: {exc}')

        self.dispose()

    def _get_positive_int_config(self, value, default: int, name: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            self.logger.warning(f'Invalid {name}: {value!r}, using {default}')
            return default
        if parsed < 1:
            self.logger.warning(f'Invalid {name}: {value!r}, using {default}')
            return default
        return parsed

    def _get_positive_float_config(self, value, default: float, name: str) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            self.logger.warning(f'Invalid {name}: {value!r}, using {default}')
            return default
        if parsed <= 0:
            self.logger.warning(f'Invalid {name}: {value!r}, using {default}')
            return default
        return parsed

    def dispose(self):
        if self.database_mode_event_bus is not None:
            self.logger.info(
                f'database_mode_event_bus_closed event_bus_instance_id={self.database_mode_event_bus.instance_id} '
                f'subscriber_count={self.database_mode_event_bus.subscriber_count}'
            )
            self.database_mode_event_bus.close()
        if self.desktop_automation_service is not None:
            self.desktop_automation_service.close()
        if self.local_connectors_service is not None:
            self.local_connectors_service.dispose()
        if self.plugin_connector is not None:
            self.plugin_connector.dispose()
        if self.box_service is not None:
            self.box_service.dispose()

    async def print_web_access_info(self):
        """Print access webui tips"""

        from ..utils import paths

        frontend_path = paths.get_frontend_path()

        if not os.path.exists(frontend_path):
            self.logger.warning('WebUI 文件缺失，请根据文档部署：https://docs.langbot.app/zh')
            self.logger.warning(
                'WebUI files are missing, please deploy according to the documentation: https://docs.langbot.app/en'
            )
            return

        host_ip = '127.0.0.1'

        port = self.instance_config.data['api']['port']

        tips = f"""
=======================================
✨ Access WebUI / 访问管理面板

🏠 Local Address: http://{host_ip}:{port}/
🌐 Public Address: http://<Your Public IP>:{port}/

📌 Running this program in a container? Please ensure that the {port} port is exposed
=======================================
""".strip()
        for line in tips.split('\n'):
            self.logger.info(line)
