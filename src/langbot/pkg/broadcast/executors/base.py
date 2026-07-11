from __future__ import annotations

from typing import Any


class ConversationDraftExecutor:
    channel = 'unknown'

    def validate_capability(self, action: str) -> dict[str, Any]:
        raise NotImplementedError

    async def health_check(self) -> dict[str, Any]:
        raise NotImplementedError

    async def paste_draft(
        self,
        *,
        conversation_name: str,
        draft_text: str,
        idempotency_key: str,
        request_digest: str,
        attachment_root: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def send_message(
        self,
        *,
        conversation_name: str,
        message_text: str,
        idempotency_key: str,
        request_digest: str,
        attachment_root: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def cancel(self, runtime_task_id: str) -> dict[str, Any]:
        raise NotImplementedError

    async def query_status(self, runtime_task_id: str) -> dict[str, Any]:
        raise NotImplementedError

    def normalize_evidence(self, result: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
