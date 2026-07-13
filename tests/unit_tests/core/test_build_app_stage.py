from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from langbot.pkg.core.stages.build_app import BuildAppStage


@pytest.mark.asyncio
async def test_packaged_onboarding_loads_adapter_catalog_without_starting_platform_runtime(monkeypatch):
    onboarding_initialize = AsyncMock()
    runtime_initialize = AsyncMock()

    class PlatformManager:
        def __init__(self, *, ap):
            self.ap = ap

        initialize_onboarding = onboarding_initialize
        initialize = runtime_initialize

    monkeypatch.setattr('langbot.pkg.core.stages.build_app.im_mgr.PlatformManager', PlatformManager)
    app = SimpleNamespace()

    await BuildAppStage()._initialize_onboarding_core(app)

    assert app.platform_mgr is not None
    onboarding_initialize.assert_awaited_once()
    runtime_initialize.assert_not_awaited()


@pytest.mark.asyncio
async def test_build_app_stage_restores_local_connectors_only_once(monkeypatch):
    restore_mock = AsyncMock()
    initialize_builtin_mock = AsyncMock()
    watcher_args: dict[str, object] = {}

    def local_connectors_factory(_ap):
        return SimpleNamespace(
            initialize_builtin_mcp_servers=initialize_builtin_mock,
            restore_configured_connectors=restore_mock,
        )

    async def noop_async(*_args, **_kwargs):
        return None

    def object_with_initialize(*_args, **_kwargs):
        return SimpleNamespace(initialize=AsyncMock(side_effect=noop_async))

    platform_onboarding_initialize = AsyncMock(side_effect=noop_async)
    platform_runtime_initialize = AsyncMock(side_effect=noop_async)

    def platform_manager_factory(*_args, **_kwargs):
        return SimpleNamespace(
            initialize_onboarding=platform_onboarding_initialize,
            initialize=platform_runtime_initialize,
        )

    persistence_initialize = AsyncMock(side_effect=noop_async)
    seed_space_model_providers = AsyncMock(side_effect=noop_async)

    def persistence_manager_factory(*_args, **_kwargs):
        return SimpleNamespace(
            initialize=persistence_initialize,
            write_space_model_providers=seed_space_model_providers,
        )

    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.local_connectors_service.LocalConnectorsService',
        local_connectors_factory,
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.proxy.ProxyManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.version.VersionManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.storagemgr.StorageMgr', object_with_initialize)
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.persistencemgr.PersistenceManager',
        persistence_manager_factory,
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.telemetry_module.TelemetryManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.survey_module.SurveyManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.cmdmgr.CommandManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.llm_model_mgr.ModelManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.llm_session_mgr.SessionManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.box_service.BoxService', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.llm_tool_mgr.ToolManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.im_mgr.PlatformManager', platform_manager_factory)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.rag_mgr.RAGManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.vectordb_mgr.VectorDBManager', object_with_initialize)
    def http_controller_factory(*_args, **_kwargs):
        async def before_serving(func):
            return func

        async def after_serving(func):
            return func

        return SimpleNamespace(
            initialize=AsyncMock(side_effect=noop_async),
            quart_app=SimpleNamespace(
                before_serving=lambda func: func,
                after_serving=lambda func: func,
            ),
        )

    monkeypatch.setattr('langbot.pkg.core.stages.build_app.http_controller.HTTPController', http_controller_factory)

    monkeypatch.setattr('langbot.pkg.core.stages.build_app.RAGRuntimeService', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.WebhookPusher', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.pipelinemgr.PipelineManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.message_aggregator.MessageAggregator', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.skill_mgr.SkillManager', object_with_initialize)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.monitoring_service.MonitoringService', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.DatabaseModeEventBus',
        lambda *_args, **_kwargs: SimpleNamespace(instance_id='bus-1', subscriber_count=0),
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.database_mode_service.DatabaseModeService', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.database_mode_processing_service.DatabaseModeProcessingService',
        lambda *_args, **_kwargs: SimpleNamespace(reconcile_stale_processing_runs=AsyncMock(side_effect=noop_async)),
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.BroadcastService', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.BroadcastExecutionWorker',
        lambda *_args, **_kwargs: SimpleNamespace(start=AsyncMock(side_effect=noop_async), stop=AsyncMock(side_effect=noop_async)),
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.DesktopAutomationRepository', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.DesktopRuntimeProcessManager', lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.DesktopAutomationService',
        lambda *_args, **_kwargs: SimpleNamespace(reconcile_stale_runs=AsyncMock(side_effect=noop_async)),
    )
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.build_local_shutdown_watcher_from_env',
        lambda **kwargs: watcher_args.update(kwargs) or None,
    )
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.plugin_connector.PluginRuntimeConnector',
        lambda *_args, **_kwargs: SimpleNamespace(initialize=AsyncMock(side_effect=noop_async)),
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.controller.Controller', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.maintenance_service.MaintenanceService', lambda *_args, **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        'langbot.pkg.core.stages.build_app.discover_engine.ComponentDiscoveryEngine',
        lambda *_args, **_kwargs: SimpleNamespace(discover_blueprint=lambda *_a, **_k: None),
    )
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.apply_local_desktop_automation_defaults', lambda config: config)
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.paths.get_data_root', lambda: str(Path.cwd() / 'data'))
    monkeypatch.setattr('langbot.pkg.core.stages.build_app.paths.get_repo_root', lambda: str(Path.cwd()))

    for target in [
        'user_service.UserService',
        'space_service.SpaceService',
        'model_service.LLMModelsService',
        'model_service.EmbeddingModelsService',
        'model_service.RerankModelsService',
        'provider_service.ModelProviderService',
        'pipeline_service.PipelineService',
        'bot_service.BotService',
        'knowledge_service.KnowledgeService',
        'mcp_service.MCPService',
        'apikey_service.ApiKeyService',
        'webhook_service.WebhookService',
        'skill_service.SkillService',
    ]:
        monkeypatch.setattr(f'langbot.pkg.core.stages.build_app.{target}', lambda *_args, **_kwargs: SimpleNamespace())

    states: list[object] = []
    app = SimpleNamespace(
        instance_config=SimpleNamespace(data={'desktop_automation': {}, 'api': {'port': 5302}}),
        logger=SimpleNamespace(info=lambda *_args, **_kwargs: None),
        http_ctrl=None,
        set_runtime_state=lambda state, **_kwargs: states.append(state),
    )

    stage = BuildAppStage()
    await stage.run(app)

    assert initialize_builtin_mock.await_count == 1
    assert restore_mock.await_count == 1
    platform_onboarding_initialize.assert_awaited_once()
    platform_runtime_initialize.assert_awaited_once()
    seed_space_model_providers.assert_awaited_once()
    assert watcher_args['repo_root'] == Path.cwd()
    assert states
