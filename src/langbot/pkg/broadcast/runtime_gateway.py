from __future__ import annotations

import os
from typing import Any

from .errors import (
    BROADCAST_EXECUTION_SAFETY_LOCK_REQUIRED,
    BroadcastError,
)


class BroadcastRuntimeGateway:
    def __init__(self, runtime_client) -> None:
        self.runtime_client = runtime_client

    async def health_check(self) -> dict[str, Any]:
        return await self.runtime_client.health()

    async def get_capabilities(self) -> dict[str, Any]:
        return await self.runtime_client.capabilities()

    def assert_force_disable_send(self) -> None:
        if str(os.environ.get('LANGBOT_RPA_FORCE_DISABLE_SEND') or '').strip() != '1':
            raise BroadcastError(
                BROADCAST_EXECUTION_SAFETY_LOCK_REQUIRED,
                '未开启强制禁用发送安全锁，禁止执行写入任务',
            )

    async def create_paste_task(
        self,
        *,
        conversation_name: str,
        draft_text: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, Any]:
        return await self.runtime_client.create_task(
            request={
                'action': 'paste_draft',
                'conversationName': conversation_name,
                'draftText': draft_text,
                'idempotencyKey': idempotency_key,
                'requestDigest': request_digest,
            }
        )

    async def create_send_task(
        self,
        *,
        conversation_name: str,
        message_text: str,
        idempotency_key: str,
        request_digest: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        return await self.runtime_client.create_task(
            request={
                'action': 'send_message',
                'conversationName': conversation_name,
                'messageText': message_text,
                'idempotencyKey': idempotency_key,
                'requestDigest': request_digest,
                'confirmationToken': confirmation_token,
            }
        )

    async def query_task(self, runtime_task_id: str) -> dict[str, Any]:
        return await self.runtime_client.get_task(runtime_task_id)

    async def cancel_task(self, runtime_task_id: str) -> dict[str, Any]:
        return await self.runtime_client.cancel_task(runtime_task_id)
