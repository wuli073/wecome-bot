from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


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
        return bool(str(connector_id or '').strip())

    def is_scope_send_enabled(self, connector_id: str | None) -> bool:
        return self.send_enabled and self.is_connector_allowed(connector_id)

    def to_runtime_environment(self) -> dict[str, str]:
        return {
            'LANGBOT_BROADCAST_SEND_ENABLED': '1',
            'LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS': '*',
        }


def resolve_broadcast_send_gate(
    *,
    broadcast_config: Mapping[str, Any] | None = None,
    env: Mapping[str, Any] | None = None,
) -> BroadcastSendGateSnapshot:
    del broadcast_config, env
    return BroadcastSendGateSnapshot(
        requested_enabled=True,
        send_enabled=True,
        allowed_connectors=('*',),
        allowed_connector_count=0,
        error_code=None,
        env_connectors=('*',),
        config_bindings={},
    )
