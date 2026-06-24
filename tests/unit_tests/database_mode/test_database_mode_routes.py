from __future__ import annotations

import sys
import types
import datetime
from types import SimpleNamespace

import jwt
import pytest
import quart

core_app_stub = types.ModuleType("langbot.pkg.core.app")
core_app_stub.Application = object
sys.modules.setdefault("langbot.pkg.core.app", core_app_stub)

from langbot.pkg.api.http.controller.groups.database_mode import DatabaseModeRouterGroup
from langbot.pkg.database_mode.events import DatabaseModeEventBus


pytestmark = pytest.mark.asyncio


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
    return app.test_client(), ap, scheme


def _decode_cookie(cookie_value: str, secret: str) -> dict:
    return jwt.decode(cookie_value, secret, algorithms=["HS256"])


async def test_handshake_returns_204_and_sets_cookie():
    client, ap, scheme = await _make_client()

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
    client, _ap, _scheme = await _make_client(scheme="https")

    response = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme="https",
    )

    assert response.status_code == 204
    assert "Secure" in response.headers["Set-Cookie"]


async def test_stream_rejects_missing_cookie():
    client, _ap, scheme = await _make_client()

    response = await client.get("/api/v1/database-mode/events", scheme=scheme)
    payload = await response.get_json()

    assert response.status_code == 401
    assert payload["msg"] == "Missing SSE session cookie"


async def test_stream_rejects_expired_cookie():
    client, ap, scheme = await _make_client()
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
    client, ap, scheme = await _make_client(user_exists=False)
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


async def test_stream_ignores_last_event_id_and_emits_ready():
    client, ap, scheme = await _make_client()

    handshake = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme=scheme,
    )
    set_cookie = handshake.headers["Set-Cookie"]
    cookie_value = set_cookie.split("langbot_dbmode_sse=", 1)[1].split(";", 1)[0]
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
        await connection.disconnect()
        ap.database_mode_event_bus.close()
        response = await connection.as_response()

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Content-Encoding"] == "identity"
    assert response.headers["X-Accel-Buffering"] == "no"


async def test_stream_works_without_last_event_id():
    client, ap, scheme = await _make_client()

    handshake = await client.post(
        "/api/v1/database-mode/events/session",
        headers={"Authorization": "Bearer valid-user-token"},
        scheme=scheme,
    )
    set_cookie = handshake.headers["Set-Cookie"]
    cookie_value = set_cookie.split("langbot_dbmode_sse=", 1)[1].split(";", 1)[0]

    async with client.request(
        "/api/v1/database-mode/events",
        method="GET",
        headers={"Cookie": f"langbot_dbmode_sse={cookie_value}"},
        scheme=scheme,
    ) as connection:
        initial_chunk = await connection.receive()
        assert b"event: ready\n" in initial_chunk
        await connection.disconnect()
        ap.database_mode_event_bus.close()
        response = await connection.as_response()

    assert response.status_code == 200


async def test_sse_preflight_returns_credentialed_cors_headers_for_allowed_origin():
    client, _ap, scheme = await _make_client()
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
    client, _ap, scheme = await _make_client()
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
    client, _ap, scheme = await _make_client()

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
    client, _ap, scheme = await _make_client()
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
