from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import quart

from langbot.pkg.database_mode.service import EventIngestResult
from langbot.pkg.local_connectors.routes import LocalConnectorsRouterGroup


pytestmark = pytest.mark.asyncio


async def _make_client(*, allow_loopback: bool, valid_token: bool, ingest_side_effect=None, ingest_result=None):
    app = quart.Quart(__name__)
    ap = SimpleNamespace(
        local_connectors_service=SimpleNamespace(
            is_loopback_request=lambda _addr: allow_loopback,
            validate_internal_event_token=lambda _connector_id, _token: valid_token,
        ),
        database_mode_service=SimpleNamespace(
            ingest_internal_event=AsyncMock(
                side_effect=ingest_side_effect,
                return_value=ingest_result
                or EventIngestResult(accepted=True, duplicate=False, event_id="evt-1"),
            )
        ),
    )
    router = LocalConnectorsRouterGroup(ap, app)
    await router.initialize()
    return app.test_client(), ap


async def test_internal_event_route_rejects_non_loopback_requests():
    client, _ap = await _make_client(allow_loopback=False, valid_token=True)

    response = await client.post(
        "/api/v1/local-connectors/internal/events",
        headers={"X-Wecome-Connector-Token": "token"},
        json={},
    )

    assert response.status_code == 403


async def test_internal_event_route_rejects_invalid_token():
    client, _ap = await _make_client(allow_loopback=True, valid_token=False)

    response = await client.post(
        "/api/v1/local-connectors/internal/events",
        headers={"X-Wecome-Connector-Token": "bad-token"},
        json={},
    )

    assert response.status_code == 401


async def test_internal_event_route_returns_bad_request_for_invalid_payload():
    client, ap = await _make_client(
        allow_loopback=True,
        valid_token=True,
        ingest_side_effect=ValueError("event_id and message_key are required"),
    )

    response = await client.post(
        "/api/v1/local-connectors/internal/events",
        headers={"X-Wecome-Connector-Token": "token"},
        json={},
    )
    payload = await response.get_json()

    assert response.status_code == 400
    assert payload["msg"] == "event_id and message_key are required"
    ap.database_mode_service.ingest_internal_event.assert_awaited_once_with({})


async def test_internal_event_route_accepts_valid_payload():
    client, ap = await _make_client(
        allow_loopback=True,
        valid_token=True,
        ingest_result=EventIngestResult(accepted=True, duplicate=True, event_id="evt-2"),
    )
    event_payload = {
        "connector_id": "wxwork-local",
        "event_id": "evt-2",
        "message_key": "wxwork:key",
    }

    response = await client.post(
        "/api/v1/local-connectors/internal/events",
        headers={"X-Wecome-Connector-Token": "token"},
        json=event_payload,
    )
    payload = await response.get_json()

    assert response.status_code == 200
    assert payload["data"] == {
        "accepted": True,
        "duplicate": True,
        "event_id": "evt-2",
    }
    ap.database_mode_service.ingest_internal_event.assert_awaited_once_with(event_payload)


async def test_internal_event_route_rejects_payloads_over_limit():
    client, _ap = await _make_client(allow_loopback=True, valid_token=True)

    response = await client.post(
        "/api/v1/local-connectors/internal/events",
        headers={
            "X-Wecome-Connector-Token": "token",
            "Content-Type": "application/json",
            "Content-Length": str(70 * 1024),
        },
        data="{}",
    )

    assert response.status_code == 413
