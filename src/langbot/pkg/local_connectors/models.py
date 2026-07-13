from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinConnectorDefinition:
    connector_id: str
    name: str
    url: str
    tool_count: int

    @property
    def mcp_payload(self) -> dict:
        return {
            "name": self.name,
            "mode": "remote",
            "enable": False,
            "extra_args": {"url": self.url},
            "builtin": True,
            "locked": True,
            "managed_by": "local_connectors",
            "connector_id": self.connector_id,
        }


BUILTIN_CONNECTORS: tuple[BuiltinConnectorDefinition, ...] = (
    BuiltinConnectorDefinition(
        connector_id="wechat-local",
        name="微信解密",
        url="http://127.0.0.1:5680/mcp",
        tool_count=17,
    ),
    BuiltinConnectorDefinition(
        connector_id="wxwork-local",
        name="企业微信",
        url="http://127.0.0.1:5681/mcp",
        tool_count=5,
    ),
)
