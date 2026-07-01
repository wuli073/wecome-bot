"""
API smoke integration tests.

Tests real HTTP API behavior using Quart test client.
Validates controller/service/routing wiring without real provider/platform.

Run: uv run pytest tests/integration/api/test_smoke.py -q
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import urllib.request

import pytest
from unittest.mock import MagicMock, AsyncMock, Mock

from tests.factories import FakeApp


pytestmark = pytest.mark.integration


def _get_free_tcp_port(host: str = '127.0.0.1') -> int:
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


async def _fetch_json(url: str) -> tuple[int, dict]:
    def _request():
        with urllib.request.urlopen(url, timeout=3) as response:
            return response.status, json.loads(response.read().decode('utf-8'))

    return await asyncio.to_thread(_request)


# ============== FIXTURE FOR SYS.MODULES ISOLATION ==============


@pytest.fixture(scope='module')
def mock_circular_import_chain():
    """
    Break circular import chain for API controller using isolated_sys_modules.

    Chain: http_controller → groups/plugins → core.app → pipeline entities

    We need to mock core.app to prevent the circular chain when importing HTTPController.
    But we must allow groups to be imported to populate preregistered_groups.
    """
    from tests.utils.import_isolation import isolated_sys_modules, MockLifecycleControlScope

    # Mock core.app with minimal Application that groups can reference
    class FakeMinimalApplication:
        pass

    mock_app = MagicMock()
    mock_app.Application = FakeMinimalApplication

    # Mock core.entities with proper Enum
    mock_entities = MagicMock()
    mock_entities.LifecycleControlScope = MockLifecycleControlScope

    # Modules to clear (force re-import after mocking)
    clear = [
        'langbot.pkg.api.http.controller.group',
        'langbot.pkg.api.http.controller.groups',
        'langbot.pkg.api.http.controller.groups.system',
        'langbot.pkg.api.http.controller.groups.user',
        'langbot.pkg.api.http.controller.main',
    ]

    with isolated_sys_modules(
        mocks={
            'langbot.pkg.core.app': mock_app,
            'langbot.pkg.core.entities': mock_entities,
        },
        clear=clear,
    ):
        # Import groups after mocking core.app/core.entities
        import langbot.pkg.api.http.controller.group as _group_module  # noqa: E402, F401
        import langbot.pkg.api.http.controller.groups.system as _system_group  # noqa: E402, F401
        import langbot.pkg.api.http.controller.groups.user as _user_group  # noqa: E402, F401

        yield


# ============== FAKE APPLICATION FOR API TESTS ==============


@pytest.fixture
def fake_api_app():
    """
    Create minimal FakeApp for API smoke tests with all required services.

    Uses tests.factories.FakeApp as base and adds API-specific services.
    """
    app = FakeApp()

    # API-specific config
    app.instance_config.data.update(
        {
            'api': {'port': 5300},
            'plugin': {'enable_marketplace': True},
            'space': {'url': 'https://space.langbot.app'},
            'system': {'allow_modify_login_info': True, 'limitation': {}},
        }
    )

    # API-specific services
    app.user_service = Mock()
    app.user_service.is_initialized = AsyncMock(return_value=False)
    app.user_service.authenticate = AsyncMock(return_value='fake_token')
    app.user_service.create_user = AsyncMock()
    app.user_service.verify_jwt_token = AsyncMock(side_effect=ValueError('Invalid token'))
    app.user_service.get_user_by_email = AsyncMock(return_value=Mock())
    app.user_service.generate_jwt_token = AsyncMock(return_value='fake_token')

    app.apikey_service = Mock()
    app.apikey_service.verify_api_key = AsyncMock(return_value=True)

    app.maintenance_service = Mock()
    app.maintenance_service.get_storage_analysis = AsyncMock(return_value={})

    app.plugin_connector.is_enable_plugin = False
    app.plugin_connector.ping_plugin_runtime = AsyncMock()

    app.task_mgr.get_tasks_dict = Mock(return_value={'tasks': []})
    app.task_mgr.get_task_by_id = Mock(return_value=None)

    # Required by controller groups
    app.model_mgr = Mock()
    app.platform_mgr = Mock()
    app.pipeline_pool = Mock()
    app.pipeline_mgr = Mock()

    return app


# ============== QUART TEST CLIENT FIXTURE ==============


@pytest.fixture
async def quart_test_client(fake_api_app, http_controller_cls):
    """
    Create Quart test client with real HTTPController and route registration.

    Requires mock_circular_import_chain fixture to run first (usefixtures).
    """
    controller = http_controller_cls(fake_api_app)
    await controller.initialize()

    client = controller.quart_app.test_client()

    yield client


# ============== API SMOKE TESTS ==============


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestHealthEndpoint:
    """Tests for /healthz endpoint - simplest smoke test."""

    @pytest.mark.asyncio
    async def test_healthz_returns_ok(self, quart_test_client):
        """
        /healthz endpoint returns {'code': 0, 'msg': 'ok'}.

        This tests:
        - HTTPController instantiation
        - Quart app creation
        - Route registration
        - Basic response handling
        """
        response = await quart_test_client.get('/healthz')

        assert response.status_code == 200
        data = await response.get_json()
        assert data == {'code': 0, 'msg': 'ok'}

    @pytest.mark.asyncio
    async def test_healthz_no_auth_required(self, quart_test_client):
        """
        /healthz doesn't require authentication.

        Tests that AuthType.NONE endpoints work without headers.
        """
        response = await quart_test_client.get('/healthz')
        assert response.status_code == 200


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestSystemEndpoint:
    """Tests for /api/v1/system endpoints."""

    @pytest.mark.asyncio
    async def test_system_info_no_auth(self, quart_test_client):
        """
        /api/v1/system/info returns system information without auth.

        AuthType.NONE endpoint.
        """
        response = await quart_test_client.get('/api/v1/system/info')

        assert response.status_code == 200
        data = await response.get_json()

        # Verify response structure
        assert data['code'] == 0
        assert data['msg'] == 'ok'
        assert 'data' in data

        # Verify expected fields
        system_data = data['data']
        assert 'version' in system_data
        assert 'debug' in system_data
        assert 'edition' in system_data

    @pytest.mark.asyncio
    async def test_system_info_responds_when_list_plugins_hangs(self, fake_api_app, http_controller_cls):
        """system/info must not depend on plugin runtime list_plugins completing."""

        async def never_returns():
            await asyncio.Event().wait()

        fake_api_app.plugin_connector.list_plugins = never_returns
        controller = http_controller_cls(fake_api_app)
        await controller.initialize()
        client = controller.quart_app.test_client()

        response = await asyncio.wait_for(client.get('/api/v1/system/info'), timeout=1)

        assert response.status_code == 200
        data = await response.get_json()
        assert data['code'] == 0


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestHttpBind:
    """Tests for HTTP bind host selection."""

    @pytest.mark.asyncio
    async def test_run_starts_http_service_on_free_port(self, fake_api_app, http_controller_cls):
        """HTTPController should start a real HTTP listener and answer system/info."""
        port = _get_free_tcp_port()
        fake_api_app.instance_config.data['api']['port'] = port
        controller = http_controller_cls(fake_api_app)
        await controller.initialize()

        run_task = None
        try:
            run_task = asyncio.create_task(controller.run())
            await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port), timeout=5)

            status_code, payload = await _fetch_json(f'http://127.0.0.1:{port}/api/v1/system/info')

            assert status_code == 200
            assert payload['code'] == 0
        finally:
            if run_task is not None:
                run_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await run_task

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))

    def test_run_fails_fast_when_port_is_occupied(self, fake_api_app, http_controller_cls, caplog):
        """HTTPController.run must fail before any success logs when bind is impossible."""
        port = _get_free_tcp_port()
        fake_api_app.instance_config.data['api']['port'] = port
        controller = http_controller_cls(fake_api_app)

        occupier = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupier.bind(('127.0.0.1', port))
        occupier.listen(socket.SOMAXCONN)

        try:
            with pytest.raises(RuntimeError, match='(?i)(address already in use|port occupied)'):
                controller.run()

            assert 'Local Address:' not in caplog.text
            assert 'Running on http://' not in caplog.text
        finally:
            occupier.close()

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))

    def test_default_bind_host_is_loopback(self, fake_api_app, http_controller_cls):
        """Default local service bind should own 127.0.0.1, not only wildcard."""
        controller = http_controller_cls(fake_api_app)

        assert controller._get_bind_host() == '127.0.0.1'

    def test_configured_bind_host_is_respected(self, fake_api_app, http_controller_cls, monkeypatch):
        """Operators can still opt into a public/container bind host explicitly."""
        fake_api_app.instance_config.data['api']['host'] = '0.0.0.0'
        controller = http_controller_cls(fake_api_app)
        captured_bind: list[str] = []

        assert controller._get_bind_host() == '0.0.0.0'

        def fake_reserve_sockets(config):
            captured_bind.extend(config.bind)
            from types import SimpleNamespace

            return SimpleNamespace(secure_sockets=[], insecure_sockets=[], quic_sockets=[])

        async def fake_run_with_readiness(*, config, sockets):
            return None

        monkeypatch.setattr(controller, '_reserve_sockets', fake_reserve_sockets)
        monkeypatch.setattr(controller, '_run_with_readiness', fake_run_with_readiness)

        run_coro = controller.run()
        assert captured_bind == ['0.0.0.0:5300']
        run_coro.close()

    @pytest.mark.asyncio
    async def test_run_propagates_serve_startup_exception(self, fake_api_app, http_controller_cls, monkeypatch):
        """Startup exceptions from the underlying server coroutine must bubble out cleanly."""
        port = _get_free_tcp_port()
        fake_api_app.instance_config.data['api']['port'] = port
        controller = http_controller_cls(fake_api_app)
        await controller.initialize()

        async def broken_serve(*, config, sockets, shutdown_trigger, ready_future):
            raise RuntimeError('startup boom')

        try:
            monkeypatch.setattr(controller, '_run_task', broken_serve)
            with pytest.raises(RuntimeError, match='startup boom'):
                await asyncio.create_task(controller.run())
        finally:
            pass

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(('127.0.0.1', port))


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestProtectedEndpoints:
    """Tests for authentication/authorization behavior."""

    @pytest.mark.asyncio
    async def test_protected_endpoint_rejects_no_token(self, quart_test_client):
        """
        Protected endpoint (USER_TOKEN) returns 401 without auth.

        Tests that AuthType.USER_TOKEN properly rejects unauthorized requests.
        """
        # /api/v1/user/check-token requires USER_TOKEN
        response = await quart_test_client.get('/api/v1/user/check-token')

        assert response.status_code == 401
        data = await response.get_json()

        # Verify error response structure
        assert data['code'] == -1
        assert 'msg' in data

    @pytest.mark.asyncio
    async def test_protected_endpoint_with_invalid_token(self, quart_test_client):
        """
        Protected endpoint returns 401 with invalid token.
        """
        response = await quart_test_client.get(
            '/api/v1/user/check-token', headers={'Authorization': 'Bearer invalid_token'}
        )

        assert response.status_code == 401


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestInvalidPayload:
    """Tests for error handling with invalid payloads."""

    @pytest.mark.asyncio
    async def test_missing_json_body(self, quart_test_client):
        """
        POST endpoint without JSON body handles gracefully.
        """
        # /api/v1/user/auth expects JSON with 'user' and 'password'
        response = await quart_test_client.post('/api/v1/user/auth')

        # Should return error (500, 400, or 401) with stable JSON structure
        assert response.status_code in (400, 500, 401)
        data = await response.get_json()

        # Verify error response has expected structure
        assert 'code' in data
        assert 'msg' in data

    @pytest.mark.asyncio
    async def test_invalid_json_structure(self, quart_test_client):
        """
        POST with wrong JSON structure returns stable error.
        """
        response = await quart_test_client.post('/api/v1/user/auth', json={'wrong_field': 'value'})

        # Should return error with stable JSON structure
        assert response.status_code in (400, 500, 401)
        data = await response.get_json()
        assert 'code' in data
        assert 'msg' in data


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestUserInitEndpoint:
    """Tests for /api/v1/user/init endpoint."""

    @pytest.mark.asyncio
    async def test_user_init_get_returns_not_initialized(self, quart_test_client):
        """
        GET /api/v1/user/init returns initialized status.

        Uses fake user_service.is_initialized() = False.
        """
        response = await quart_test_client.get('/api/v1/user/init')

        assert response.status_code == 200
        data = await response.get_json()

        assert data['code'] == 0
        assert data['msg'] == 'ok'
        assert data['data']['initialized'] is False


@pytest.mark.usefixtures('mock_circular_import_chain')
class TestRealImports:
    """Tests that verify real production code is imported."""

    def test_http_controller_real_import(self):
        """
        Verify HTTPController is real production class, not mock.
        """
        from langbot.pkg.api.http.controller.main import HTTPController

        assert HTTPController.__name__ == 'HTTPController'
        assert hasattr(HTTPController, 'initialize')
        assert hasattr(HTTPController, 'register_routes')

    def test_group_real_import(self):
        """
        Verify RouterGroup and AuthType are real production classes.
        """
        from langbot.pkg.api.http.controller.group import RouterGroup, AuthType, preregistered_groups

        assert RouterGroup.__name__ == 'RouterGroup'
        assert hasattr(AuthType, 'NONE')
        assert hasattr(AuthType, 'USER_TOKEN')
        assert isinstance(preregistered_groups, list)

    def test_system_group_registered(self):
        """
        Verify SystemRouterGroup is registered in preregistered_groups.
        """
        from langbot.pkg.api.http.controller.group import preregistered_groups

        # Find system group
        system_group = None
        for g in preregistered_groups:
            if g.name == 'system':
                system_group = g
                break

        assert system_group is not None
        assert system_group.path == '/api/v1/system'

    def test_user_group_registered(self):
        """
        Verify UserRouterGroup is registered in preregistered_groups.
        """
        from langbot.pkg.api.http.controller.group import preregistered_groups

        # Find user group
        user_group = None
        for g in preregistered_groups:
            if g.name == 'user':
                user_group = g
                break

        assert user_group is not None
        assert user_group.path == '/api/v1/user'
