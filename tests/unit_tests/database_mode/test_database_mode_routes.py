from __future__ import annotations

import asyncio
import sys
import types
import datetime
from types import SimpleNamespace

import jwt
import pytest
import quart

core_app_stub = types.ModuleType("langbot.pkg.core.app")
core_app_stub.Application = object
_previous_core_app_module = sys.modules.get("langbot.pkg.core.app")
sys.modules["langbot.pkg.core.app"] = core_app_stub

from langbot.pkg.api.http.controller.groups.database_mode import DatabaseModeRouterGroup
from langbot.pkg.database_mode.events import DatabaseModeEventBus

if _previous_core_app_module is not None:
    sys.modules["langbot.pkg.core.app"] = _previous_core_app_module
else:
    sys.modules.pop("langbot.pkg.core.app", None)


pytestmark = pytest.mark.asyncio


import langbot.pkg.api.http.controller.groups.database_mode as database_mode_module
from langbot.pkg.database_mode.events import (
    DatabaseModeEvent,
    DatabaseModeEventBus,
    DatabaseModeEventType,
)


def _user_record(email: str = "user@example.com") -> SimpleNamespace:
    return SimpleNamespace(user=email)


async def _make_client(*, scheme: str = "http", user_exists: bool = True):
    app = quart.Quart(__name__)
    verified_user_email = "user@example.com"

    async def verify_jwt_token(_token: str) -> str:
        return verified_user_email

    async def get_user_by_email(_email: str):
        if not user_exists:
            return None
        return _user_record(verified_user_email)

    ap = SimpleNamespace(
        instance_config=SimpleNamespace(
            data={
                "system": {
                    "jwt": {
                        "secret": "test-secret",
                        "expire": 3600,
                    }
                }
            }
        ),
        user_service=SimpleNamespace(
            verify_jwt_token=verify_jwt_token,
            get_user_by_email=get_user_by_email,
        ),
        database_mode_service=SimpleNamespace(),
        database_mode_event_bus=DatabaseModeEventBus(),
    )

    router = DatabaseModeRouterGroup(ap, app)
    await router.initialize()
    return app, app.test_client(), ap, scheme


def _decode_cookie(cookie_value: str, secret: str) -> dict:
    return jwt.decode(cookie_value, secret, algorithms=["HS256"])


async def test_handshake_returns_204_and_sets_cookie():
    _app, client, ap, scheme = await _make_client()

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme=scheme,
    )

    assert response.status_code == 204
    assert response.headers["Cache-Control"] == "no-store"

    set_cookie = response.headers.get("Set-Cookie")
    assert set_cookie is not None
    assert "langbot_dbmode_sse=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Strict" in set_cookie
    assert "Path=/api/v1/database-mode/events" in set_cookie
    assert "Domain=" not in set_cookie
    assert "Secure" not in set_cookie

    cookie_value = set_cookie.split("langbot_dbmode_sse=", 1)[1].split(";", 1)[0]
    payload = _decode_cookie(cookie_value, ap.instance_config.data["system"]["jwt"]["secret"])
    assert payload["version"] == 1
    assert payload["purpose"] == "database-mode-sse"
    assert payload["sub"] == "user@example.com"
    assert payload["session_id"]
    assert payload["issued_at"]
    assert payload["expires_at"]


async def test_handshake_sets_secure_cookie_for_https():
    _app, client, _ap, _scheme = await _make_client(scheme="https")

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme="https",
    )

    assert response.status_code == 204
    assert "Secure" in response.headers["Set-Cookie"]


async def test_stream_rejects_missing_cookie():
    _app, client, _ap, scheme = await _make_client()

    response = await client.get("/api/v1/database-mode/events", scheme=scheme)
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "Missing SSE session cookie"


async def test_stream_rejects_expired_cookie():
    _app, client, ap, scheme = await _make_client()
    expired_payload = {
        "sub": "user@example.com",
        "version": 1,
        "purpose": "database-mode-sse",
        "issued_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)).isoformat(),
        "expires_at": (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)).isoformat(),
        "session_id": "expired-session",
    }
    expired_cookie = jwt.encode(
        expired_payload,
        ap.instance_config.data["system"]["jwt"]["secret"],
        algorithm="HS256",
    )

    response = await client.get(
        "/api/v1/database-mode/events",
        headers={"Cookie": f"langbot_dbmode_sse={expired_cookie}"},
        scheme=scheme,
    )
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "SSE session expired"


async def test_stream_rejects_cookie_for_deleted_user():
    _app, client, ap, scheme = await _make_client(user_exists=False)
    issued_at = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": "user@example.com",
        "version": 1,
        "purpose": "database-mode-sse",
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + datetime.timedelta(minutes=5)).isoformat(),
        "session_id": "active-session",
    }
    cookie_value = jwt.encode(
        payload,
        ap.instance_config.data["system"]["jwt"]["secret"],
        algorithm="HS256",
    )

    response = await client.get(
        "/api/v1/database-mode/events",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    )
    data = await response.get_json()

    assert response.status_code == 401
    assert data["msg"] == "User not found"


async def _create_sse_cookie(client, scheme: str) -> str:
    handshake = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme=scheme,
    )
    set_cookie = handshake.headers["Set-Cookie"]
    return set_cookie.split("langbot_dbmode_sse=", 1)[1].split(";", 1)[0]


async def _receive_until(
    connection,
    predicate,
    *,
    attempts: int = 10,
    timeout: float = 1,
):
    chunks = []
    for _ in range(attempts):
        chunk = await asyncio.wait_for(connection.receive(), timeout=timeout)
        chunks.append(chunk)
        if predicate(chunk):
            return chunk, chunks
    raise AssertionError(f"Did not receive expected chunk after {attempts} attempts: {chunks!r}")


async def test_stream_ignores_last_event_id_and_emits_ready(monkeypatch):
    app, client, ap, scheme = await _make_client()
    monkeypatch.setattr(database_mode_module, "DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    captured_response = None
    original_make_response = app.make_response

    async def capture_make_response(result):
        nonlocal captured_response
        response = await original_make_response(result)
        if quart.request.path == "/api/v1/database-mode/events":
            captured_response = response
        return response

    app.make_response = capture_make_response

    cookie_value = await _create_sse_cookie(client, scheme)
    cookie_header = f"langbot_dbmode_sse={cookie_value}"

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={
            "Cookie": cookie_header,
            "Last-Event-ID": "should-be-ignored",
        },
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        assert b'"type": "ready"' in initial_chunk
        heartbeat_one = await asyncio.wait_for(connection.receive(), timeout=1)
        heartbeat_two = await asyncio.wait_for(connection.receive(), timeout=1)
        assert heartbeat_one == b": heartbeat\n\n"
        assert heartbeat_two == b": heartbeat\n\n"
        assert ap.database_mode_event_bus.subscriber_count == 1
        await connection.disconnect()
        ap.database_mode_event_bus.close()
        response = await connection.as_response()

    assert captured_response is not None
    assert captured_response.timeout is None
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Encoding"] == "identity"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert ap.database_mode_event_bus.subscriber_count == 0


async def test_stream_business_event_is_followed_by_heartbeat(monkeypatch):
    _app, client, ap, scheme = await _make_client()
    monkeypatch.setattr(database_mode_module, "DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    cookie_value = await _create_sse_cookie(client, scheme)

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        event = DatabaseModeEvent(
            type=DatabaseModeEventType.MESSAGE_CREATED,
            message_id=7,
            occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        await ap.database_mode_event_bus.publish(event)
        business_chunk, observed_chunks = await _receive_until(
            connection,
            lambda chunk: b"event: database-message-created\n" in chunk,
        )
        assert b"event: database-message-created\n" in business_chunk
        assert f'"message_id": {event.message_id}'.encode() in business_chunk
        assert any(chunk == b": heartbeat\n\n" for chunk in observed_chunks[:-1]) or observed_chunks[0] == business_chunk
        heartbeat_chunk, _ = await _receive_until(
            connection,
            lambda chunk: chunk == b": heartbeat\n\n",
        )
        assert heartbeat_chunk == b": heartbeat\n\n"
        await connection.disconnect()
        ap.database_mode_event_bus.close()
        response = await connection.as_response()

    assert response.status_code == 200
    assert ap.database_mode_event_bus.subscriber_count == 0


async def test_stream_shutdown_sentinel_ends_stream_and_cleans_subscriber(monkeypatch):
    _app, client, ap, scheme = await _make_client()
    monkeypatch.setattr(database_mode_module, "DATABASE_MODE_SSE_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    cookie_value = await _create_sse_cookie(client, scheme)

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        assert ap.database_mode_event_bus.subscriber_count == 1
        ap.database_mode_event_bus.close()
        terminal_chunk, observed_chunks = await _receive_until(
            connection,
            lambda chunk: chunk == b"",
        )
        response = await connection.as_response()

    assert terminal_chunk == b""
    assert any(chunk == b": heartbeat\n\n" for chunk in observed_chunks[:-1]) or observed_chunks == [b""]
    assert response.status_code == 200
    assert ap.database_mode_event_bus.subscriber_count == 0


async def test_sse_preflight_returns_credentialed_cors_headers_for_allowed_origin():
    _app, client, _ap, scheme = await _make_client()
    origin = "http://127.0.0.1:3000"

    response = await client.options(
        "/api/v1/database-mode/events/session",
        headers={
            "Origin": origin,
            "Host": "127.0.0.1:5300",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
        scheme=scheme,
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Access-Control-Allow-Methods"] == "POST, GET, OPTIONS"
    assert response.headers["Access-Control-Allow-Headers"] == "Authorization, Content-Type"
    assert response.headers["Vary"] == "Origin"


async def test_sse_handshake_returns_precise_origin_and_cookie_for_allowed_origin():
    _app, client, _ap, scheme = await _make_client()
    origin = "http://127.0.0.1:3000"

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={
            "Origin": origin,
            "Host": "127.0.0.1:5300",
            "Authorization": "Bearer valid-user-token",
        },
        scheme=scheme,
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Vary"] == "Origin"
    assert response.headers.get("Set-Cookie") is not None
    assert response.headers["Access-Control-Allow-Origin"] != "*"


async def test_sse_handshake_rejects_disallowed_origin():
    _app, client, _ap, scheme = await _make_client()

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={
            "Origin": "http://localhost:3000",
            "Host": "127.0.0.1:5300",
            "Authorization": "Bearer valid-user-token",
        },
        scheme=scheme,
    )

    assert response.status_code == 403
    assert response.headers.get("Access-Control-Allow-Origin") is None
    assert response.headers.get("Access-Control-Allow-Credentials") is None
    assert response.headers["Vary"] == "Origin"


async def test_sse_stream_error_response_still_includes_credentialed_cors_headers():
    _app, client, _ap, scheme = await _make_client()
    origin = "http://127.0.0.1:3000"

    response = await client.get(
        "/api/v1/database-mode/events",
        headers={
            "Origin": origin,
            "Host": "127.0.0.1:5300",
        },
        scheme=scheme,
    )
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "Missing SSE session cookie"
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Vary"] == "Origin"
