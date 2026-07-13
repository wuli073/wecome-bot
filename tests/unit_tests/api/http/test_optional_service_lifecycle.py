from __future__ import annotations

from types import SimpleNamespace

import quart

from langbot.pkg.api.http.controller import group
from langbot.pkg.core.lifecycle import RuntimeState


class _RouterGroup(group.RouterGroup):
    async def initialize(self) -> None:
        return None


async def test_optional_service_returns_structured_initializing_response() -> None:
    app = SimpleNamespace(runtime_state=RuntimeState.CORE_READY, tool_mgr=None)
    quart_app = quart.Quart(__name__)
    router = _RouterGroup(app, quart_app)

    async with quart_app.app_context():
        response, status = router.require_optional_service('tool_mgr')
        payload = await response.get_json()

    assert status == 503
    assert payload == {'code': 50301, 'msg': 'SERVICE_INITIALIZING'}


async def test_optional_service_returns_normal_service_after_initialization() -> None:
    service = object()
    app = SimpleNamespace(runtime_state=RuntimeState.READY, tool_mgr=service)
    router = _RouterGroup(app, quart.Quart(__name__))

    assert router.require_optional_service('tool_mgr') is service


async def test_none_attribute_error_is_structured_unavailable_not_traceback() -> None:
    app = SimpleNamespace(runtime_state=RuntimeState.DEGRADED)
    quart_app = quart.Quart(__name__)
    router = _RouterGroup(app, quart_app)

    async with quart_app.app_context():
        response, status = router.optional_service_response(
            AttributeError("'NoneType' object has no attribute 'get_status'")
        )
        payload = await response.get_json()

    assert status == 503
    assert payload == {'code': 50301, 'msg': 'SERVICE_UNAVAILABLE'}
