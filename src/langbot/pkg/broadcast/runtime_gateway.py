from __future__ import annotations

import os
from typing import Any

from .errors import (
    BROADCAST_EXECUTION_SAFETY_LOCK_REQUIRED,
    BroadcastError,
)


class BroadcastRuntimeGateway:
    def __init__(self, runtime_provider) -> None:
        self.runtime_provider = runtime_provider

    async def health_check(self) -> dict[str, Any]:
        if hasattr(self.runtime_provider, 'runtime_health'):
            return await self.runtime_provider.runtime_health()
        client = self._get_direct_client()
        if client is not None:
            return await client.health()
        return await self.runtime_provider.health()

    async def get_capabilities(self) -> dict[str, Any]:
        if hasattr(self.runtime_provider, 'runtime_capabilities'):
            return await self.runtime_provider.runtime_capabilities()
        client = self._get_direct_client()
        if client is not None:
            return await client.capabilities()
        return await self.runtime_provider.capabilities()

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
        attachment_root: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request = {
            'action': 'paste_draft',
            'conversationName': conversation_name,
            'draftText': draft_text,
            'idempotencyKey': idempotency_key,
            'requestDigest': request_digest,
            'attachments': attachments or [],
        }
        if attachment_root:
            request['attachmentRoot'] = attachment_root
        if hasattr(self.runtime_provider, 'runtime_create_task'):
            return await self.runtime_provider.runtime_create_task(request)
        client = self._get_direct_client()
        if client is not None:
            return await client.create_task(request=request)
        return await self.runtime_provider.create_task(request=request)

    async def create_send_task(
        self,
        *,
        conversation_name: str,
        message_text: str,
        idempotency_key: str,
        request_digest: str,
        confirmation_token: str,
    ) -> dict[str, Any]:
        request = {
            'action': 'send_message',
            'conversationName': conversation_name,
            'messageText': message_text,
            'idempotencyKey': idempotency_key,
            'requestDigest': request_digest,
            'confirmationToken': confirmation_token,
        }
        if hasattr(self.runtime_provider, 'runtime_create_task'):
            return await self.runtime_provider.runtime_create_task(request)
        client = self._get_direct_client()
        if client is not None:
            return await client.create_task(request=request)
        return await self.runtime_provider.create_task(request=request)

    async def query_task(self, runtime_task_id: str) -> dict[str, Any]:
        if hasattr(self.runtime_provider, 'runtime_get_task'):
            return await self.runtime_provider.runtime_get_task(runtime_task_id)
        client = self._get_direct_client()
        if client is not None:
            return await client.get_task(runtime_task_id)
        return await self.runtime_provider.get_task(runtime_task_id)

    async def cancel_task(self, runtime_task_id: str) -> dict[str, Any]:
        if hasattr(self.runtime_provider, 'runtime_cancel_task'):
            return await self.runtime_provider.runtime_cancel_task(runtime_task_id)
        client = self._get_direct_client()
        if client is not None:
            return await client.cancel_task(runtime_task_id)
        return await self.runtime_provider.cancel_task(runtime_task_id)

    def _get_direct_client(self):
        client = getattr(self.runtime_provider, 'runtime_client', None)
        return client
