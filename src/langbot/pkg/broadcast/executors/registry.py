from __future__ import annotations

from ..errors import BROADCAST_EXECUTION_SEND_UNSUPPORTED, BroadcastError
from .wecom import WeComDraftExecutor


class UnsupportedDraftExecutor:
    def __init__(self, channel: str) -> None:
        self.channel = channel

    def validate_capability(self, action: str):
        raise BroadcastError(BROADCAST_EXECUTION_SEND_UNSUPPORTED, f'渠道 {self.channel} 暂不支持群发执行')


def build_executor(channel: str, gateway):
    if channel == 'wxwork_database':
        return WeComDraftExecutor(gateway)
    return UnsupportedDraftExecutor(channel)
