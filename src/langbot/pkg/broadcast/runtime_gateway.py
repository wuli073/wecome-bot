from __future__ import annotations

from typing import Any


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
        attachment_root: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        request = {
            'action': 'send_draft',
            'conversationName': conversation_name,
            'draftText': message_text,
            'idempotencyKey': idempotency_key,
            'requestDigest': request_digest,
            'attachments': attachments or [],
            'sendAuthorized': True,
            'allowAutoSend': True,
            'sendStrategy': 'enter',
        }
        if attachment_root:
            request['attachmentRoot'] = attachment_root
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
