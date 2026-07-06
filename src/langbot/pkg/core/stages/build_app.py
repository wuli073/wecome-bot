from __future__ import annotations

import asyncio
from pathlib import Path

from .. import stage, app
from ...utils import version, proxy
from ...pipeline import pool, controller, pipelinemgr
from ...pipeline import aggregator as message_aggregator
from ...box import service as box_service
from ...plugin import connector as plugin_connector
from ...command import cmdmgr
from ...provider.session import sessionmgr as llm_session_mgr
from ...provider.modelmgr import modelmgr as llm_model_mgr
from ...provider.tools import toolmgr as llm_tool_mgr
from ...rag.knowledge import kbmgr as rag_mgr
from ...rag.service import RAGRuntimeService
from ...platform import botmgr as im_mgr
from ...platform.webhook_pusher import WebhookPusher
from ...persistence import mgr as persistencemgr
from ...api.http.controller import main as http_controller
from ...api.http.service import user as user_service
from ...api.http.service import space as space_service
from ...api.http.service import model as model_service
from ...api.http.service import provider as provider_service
from ...api.http.service import pipeline as pipeline_service
from ...api.http.service import bot as bot_service
from ...api.http.service import knowledge as knowledge_service
from ...api.http.service import mcp as mcp_service
from ...api.http.service import apikey as apikey_service
from ...api.http.service import webhook as webhook_service
from ...api.http.service import monitoring as monitoring_service
from ...api.http.service import skill as skill_service
from ...skill import manager as skill_mgr
from ...api.http.service import maintenance as maintenance_service
from ...discover import engine as discover_engine
from ...storage import mgr as storagemgr
from ...utils import logcache
from ...vector import mgr as vectordb_mgr
from .. import taskmgr
from ...telemetry import telemetry as telemetry_module
from ...survey import manager as survey_module
from ...local_connectors import service as local_connectors_service
from ...database_mode.events import DatabaseModeEventBus
from ...database_mode import service as database_mode_service
from ...database_mode import processing_service as database_mode_processing_service
from ...broadcast.service import BroadcastService
from ...broadcast.worker import BroadcastExecutionWorker
from ...desktop_automation.repository import DesktopAutomationRepository
from ...desktop_automation.runtime_process import (
    DesktopRuntimeProcessManager,
    apply_local_desktop_automation_defaults,
)
from ...desktop_automation.client import DesktopRuntimeClient
from ...desktop_automation.service import DesktopAutomationService
from ...utils import paths
from .. import entities as core_entities
from ..local_shutdown_control import build_local_shutdown_watcher_from_env


@stage.stage_class('BuildAppStage')
class BuildAppStage(stage.BootingStage):
    """Build LangBot application"""

    async def run(self, ap: app.Application):
        """Build LangBot application"""
        ap.task_mgr = taskmgr.AsyncTaskManager(ap)

        discover = discover_engine.ComponentDiscoveryEngine(ap)
        discover.discover_blueprint('templates/components.yaml')
        ap.discover = discover

        user_service_inst = user_service.UserService(ap)
        ap.user_service = user_service_inst

        space_service_inst = space_service.SpaceService(ap)
        ap.space_service = space_service_inst

        llm_model_service_inst = model_service.LLMModelsService(ap)
        ap.llm_model_service = llm_model_service_inst

        embedding_models_service_inst = model_service.EmbeddingModelsService(ap)
        ap.embedding_models_service = embedding_models_service_inst

        rerank_models_service_inst = model_service.RerankModelsService(ap)
        ap.rerank_models_service = rerank_models_service_inst

        provider_service_inst = provider_service.ModelProviderService(ap)
        ap.provider_service = provider_service_inst

        pipeline_service_inst = pipeline_service.PipelineService(ap)
        ap.pipeline_service = pipeline_service_inst

        bot_service_inst = bot_service.BotService(ap)
        ap.bot_service = bot_service_inst

        knowledge_service_inst = knowledge_service.KnowledgeService(ap)
        ap.knowledge_service = knowledge_service_inst

        mcp_service_inst = mcp_service.MCPService(ap)
        ap.mcp_service = mcp_service_inst

        apikey_service_inst = apikey_service.ApiKeyService(ap)
        ap.apikey_service = apikey_service_inst

        webhook_service_inst = webhook_service.WebhookService(ap)
        ap.webhook_service = webhook_service_inst

        skill_service_inst = skill_service.SkillService(ap)
        ap.skill_service = skill_service_inst

        proxy_mgr = proxy.ProxyManager(ap)
        await proxy_mgr.initialize()
        ap.proxy_mgr = proxy_mgr

        ver_mgr = version.VersionManager(ap)
        await ver_mgr.initialize()
        ap.ver_mgr = ver_mgr

        ap.query_pool = pool.QueryPool()

        log_cache = logcache.LogCache()
        ap.log_cache = log_cache

        storage_mgr_inst = storagemgr.StorageMgr(ap)
        await storage_mgr_inst.initialize()
        ap.storage_mgr = storage_mgr_inst

        persistence_mgr_inst = persistencemgr.PersistenceManager(ap)
        ap.persistence_mgr = persistence_mgr_inst
        await persistence_mgr_inst.initialize()

        local_connectors_service_inst = local_connectors_service.LocalConnectorsService(ap)
        ap.local_connectors_service = local_connectors_service_inst
        await local_connectors_service_inst.initialize_builtin_mcp_servers()
        await local_connectors_service_inst.restore_configured_connectors()

        # Telemetry manager: attach to app so other components can call via self.ap.telemetry
        telemetry_inst = telemetry_module.TelemetryManager(ap)
        await telemetry_inst.initialize()
        ap.telemetry = telemetry_inst

        # Survey manager
        survey_inst = survey_module.SurveyManager(ap)
        await survey_inst.initialize()
        ap.survey = survey_inst

        cmd_mgr_inst = cmdmgr.CommandManager(ap)
        await cmd_mgr_inst.initialize()
        ap.cmd_mgr = cmd_mgr_inst

        llm_model_mgr_inst = llm_model_mgr.ModelManager(ap)
        ap.model_mgr = llm_model_mgr_inst
        await llm_model_mgr_inst.initialize()

        llm_session_mgr_inst = llm_session_mgr.SessionManager(ap)
        await llm_session_mgr_inst.initialize()
        ap.sess_mgr = llm_session_mgr_inst

        box_service_inst = box_service.BoxService(ap)
        await box_service_inst.initialize()
        ap.box_service = box_service_inst

        llm_tool_mgr_inst = llm_tool_mgr.ToolManager(ap)
        ap.tool_mgr = llm_tool_mgr_inst
        await llm_tool_mgr_inst.initialize()

        im_mgr_inst = im_mgr.PlatformManager(ap=ap)
        await im_mgr_inst.initialize()
        ap.platform_mgr = im_mgr_inst

        # Initialize webhook pusher
        webhook_pusher_inst = WebhookPusher(ap)
        ap.webhook_pusher = webhook_pusher_inst

        pipeline_mgr = pipelinemgr.PipelineManager(ap)
        await pipeline_mgr.initialize()
        ap.pipeline_mgr = pipeline_mgr

        # Initialize message aggregator (after pipeline_mgr, as it needs pipeline config)
        msg_aggregator_inst = message_aggregator.MessageAggregator(ap)
        ap.msg_aggregator = msg_aggregator_inst

        # Initialize skill manager
        skill_mgr_inst = skill_mgr.SkillManager(ap)
        await skill_mgr_inst.initialize()
        ap.skill_mgr = skill_mgr_inst

        rag_mgr_inst = rag_mgr.RAGManager(ap)
        await rag_mgr_inst.initialize()
        ap.rag_mgr = rag_mgr_inst

        # Initialize RAG Runtime Service for plugins
        ap.rag_runtime_service = RAGRuntimeService(ap)

        # 初始化向量数据库管理器
        vectordb_mgr_inst = vectordb_mgr.VectorDBManager(ap)
        await vectordb_mgr_inst.initialize()
        ap.vector_db_mgr = vectordb_mgr_inst

        http_ctrl = http_controller.HTTPController(ap)
        await http_ctrl.initialize()
        ap.http_ctrl = http_ctrl

        monitoring_service_inst = monitoring_service.MonitoringService(ap)
        ap.monitoring_service = monitoring_service_inst

        ap.database_mode_event_bus = DatabaseModeEventBus()
        ap.logger.info(
            f'database_mode_event_bus_created event_bus_instance_id={ap.database_mode_event_bus.instance_id} '
            f'subscriber_count={ap.database_mode_event_bus.subscriber_count}'
        )

        database_mode_service_inst = database_mode_service.DatabaseModeService(ap)
        ap.database_mode_service = database_mode_service_inst
        ap.database_mode_processing_service = database_mode_processing_service.DatabaseModeProcessingService(ap)
        await ap.database_mode_processing_service.reconcile_stale_processing_runs()
        ap.broadcast_service = BroadcastService(ap)

        desktop_automation_config = apply_local_desktop_automation_defaults(
            ap.instance_config.data.get('desktop_automation', {})
        )
        ap.instance_config.data['desktop_automation'] = desktop_automation_config
        desktop_automation_repository = DesktopAutomationRepository(ap.persistence_mgr)
        desktop_automation_runtime_process_manager = DesktopRuntimeProcessManager(
            config=desktop_automation_config,
        )
        ap.desktop_automation_service = DesktopAutomationService(
            ap,
            repository=desktop_automation_repository,
            runtime_process_manager=desktop_automation_runtime_process_manager,
            runtime_client_factory=lambda runtime_info: DesktopRuntimeClient(
                base_url=f"http://{runtime_info['host']}:{runtime_info['port']}",
                token=str(runtime_info['token']),
                expected_protocol_version=str(desktop_automation_config.get('expected_protocol_version') or '1'),
            ),
        )
        await ap.desktop_automation_service.reconcile_stale_runs()
        ap.broadcast_execution_worker = BroadcastExecutionWorker(
            service=ap.broadcast_service,
        )
        quart_app = ap.http_ctrl.quart_app

        repo_root = Path(paths.get_data_root()).resolve().parent
        watcher = build_local_shutdown_watcher_from_env(
            app=ap,
            repo_root=repo_root,
        )
        ap.local_shutdown_control_watcher = watcher
        if watcher is not None:
            ap.task_mgr.create_task(
                watcher.watch(),
                name='local-shutdown-control-watcher',
                scopes=[core_entities.LifecycleControlScope.APPLICATION],
            )

        @quart_app.before_serving
        async def _start_broadcast_execution_worker() -> None:
            await ap.broadcast_execution_worker.start()

        @quart_app.after_serving
        async def _stop_broadcast_execution_worker() -> None:
            await ap.broadcast_execution_worker.stop()

        maintenance_service_inst = maintenance_service.MaintenanceService(ap)
        ap.maintenance_service = maintenance_service_inst

        async def runtime_disconnect_callback(connector: plugin_connector.PluginRuntimeConnector) -> None:
            await asyncio.sleep(3)
            await plugin_connector_inst.initialize()

        plugin_connector_inst = plugin_connector.PluginRuntimeConnector(ap, runtime_disconnect_callback)
        await plugin_connector_inst.initialize()
        ap.plugin_connector = plugin_connector_inst

        ctrl = controller.Controller(ap)
        ap.ctrl = ctrl
