from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

BROADCAST_SEND_ALLOWLIST_REQUIRED = 'BROADCAST_SEND_ALLOWLIST_REQUIRED'


def _is_enabled_flag(value: Any) -> bool:
    return str(value or '0').strip() == '1'


def _normalize_connector_id(value: Any) -> str:
    return str(value or '').strip()


def _parse_env_connectors(raw_value: Any) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in str(raw_value or '').split(','):
        connector_id = _normalize_connector_id(raw_item)
        if not connector_id or connector_id in seen:
            continue
        seen.add(connector_id)
        normalized.append(connector_id)
    return tuple(normalized)


def _parse_config_bindings(broadcast_config: Mapping[str, Any] | None) -> dict[str, bool]:
    bindings_raw = (broadcast_config or {}).get('allow_send_connectors') or {}
    if not isinstance(bindings_raw, Mapping):
        return {}

    normalized: dict[str, bool] = {}
    for raw_connector_id, raw_allowed in bindings_raw.items():
        connector_id = _normalize_connector_id(raw_connector_id)
        if not connector_id:
            continue
        normalized[connector_id] = bool(raw_allowed)
    return normalized


@dataclass(frozen=True)
class BroadcastSendGateSnapshot:
    requested_enabled: bool
    send_enabled: bool
    allowed_connectors: tuple[str, ...]
    allowed_connector_count: int
    error_code: str | None
    env_connectors: tuple[str, ...]
    config_bindings: dict[str, bool]

    def is_connector_allowed(self, connector_id: str | None) -> bool:
        normalized = _normalize_connector_id(connector_id)
        if not normalized:
            return False
        if normalized in self.config_bindings:
            return bool(self.config_bindings[normalized])
        return normalized in self.env_connectors

    def is_scope_send_enabled(self, connector_id: str | None) -> bool:
        return self.send_enabled and self.is_connector_allowed(connector_id)

    def to_runtime_environment(self) -> dict[str, str]:
        return {
            'LANGBOT_BROADCAST_SEND_ENABLED': '1' if self.requested_enabled else '0',
            'LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS': ','.join(self.allowed_connectors),
        }


def resolve_broadcast_send_gate(
    *,
    broadcast_config: Mapping[str, Any] | None = None,
    env: Mapping[str, Any] | None = None,
) -> BroadcastSendGateSnapshot:
    env_map = env or {}
    config_bindings = _parse_config_bindings(broadcast_config)
    env_connectors = _parse_env_connectors(env_map.get('LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS'))
    requested_enabled = _is_enabled_flag((broadcast_config or {}).get('send_enabled')) or _is_enabled_flag(
        env_map.get('LANGBOT_BROADCAST_SEND_ENABLED')
    )

    allowed_connectors: list[str] = []
    seen: set[str] = set()
    for connector_id, allowed in config_bindings.items():
        if not allowed or connector_id in seen:
            continue
        seen.add(connector_id)
        allowed_connectors.append(connector_id)
    for connector_id in env_connectors:
        if connector_id in seen or connector_id in config_bindings:
            continue
        seen.add(connector_id)
        allowed_connectors.append(connector_id)

    send_enabled = requested_enabled and len(allowed_connectors) > 0
    error_code = BROADCAST_SEND_ALLOWLIST_REQUIRED if requested_enabled and not allowed_connectors else None
    return BroadcastSendGateSnapshot(
        requested_enabled=requested_enabled,
        send_enabled=send_enabled,
        allowed_connectors=tuple(allowed_connectors),
        allowed_connector_count=len(allowed_connectors),
        error_code=error_code,
        env_connectors=env_connectors,
        config_bindings=config_bindings,
    )
