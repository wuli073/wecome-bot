from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from langbot.pkg.database_mode.service import (
    DatabaseModeService,
    MESSAGE_STATUS_DRAFT_READY,
    MESSAGE_STATUS_PENDING,
    MESSAGE_STATUS_PROCESSED,
    MESSAGE_STATUS_SKIPPED,
)
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode


pytestmark = pytest.mark.asyncio


class MiniPersistenceManager:
    def __init__(self) -> None:
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def initialize(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(persistence_database_mode.LocalConnectorEvent.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseConversation.__table__.create)
            await conn.run_sync(persistence_database_mode.DatabaseMessage.__table__.create)

    async def dispose(self) -> None:
        await self.engine.dispose()

    async def execute_async(self, *args, **kwargs):
        async with self.engine.connect() as conn:
            result = await conn.execute(*args, **kwargs)
            await conn.commit()
            return result

    def serialize_model(self, model, data, masked_columns=None):
        masked_columns = masked_columns or []
        return {
            column.name: getattr(data, column.name)
            if not isinstance(getattr(data, column.name), datetime.datetime)
            else getattr(data, column.name).isoformat()
            for column in model.__table__.columns
            if column.name not in masked_columns
        }


async def _create_service():
    persistence_mgr = MiniPersistenceManager()
    await persistence_mgr.initialize()
    ap = SimpleNamespace(
        persistence_mgr=persistence_mgr,
        model_mgr=SimpleNamespace(llm_models=[]),
    )
    return DatabaseModeService(ap), ap


def _sample_payload() -> dict:
    return {
        "connector_id": "wxwork-local",
        "source": "wxwork",
        "event_id": "wxwork-local:evt-1",
        "message_key": "wxwork:key-1",
        "conversation": {
            "external_conversation_id": "S:100_200",
            "conversation_name": "Customer A",
            "conversation_type": "direct",
        },
        "message": {
            "external_message_id": "101",
            "sender_id": "200",
            "sender_name": "Customer A",
            "content": "Need pricing details",
            "message_type": "text",
            "sent_at": "2026-06-23T12:00:00",
            "observed_at": "2026-06-23T12:00:02",
        },
    }


async def test_ingest_internal_event_is_idempotent():
    service, ap = await _create_service()
    try:
        first = await service.ingest_internal_event(_sample_payload())
        second = await service.ingest_internal_event(_sample_payload())
        conversations = await service.list_conversations()
        messages = await service.list_messages(conversations["conversations"][0]["id"])

        assert first.accepted is True
        assert first.duplicate is False
        assert second.accepted is True
        assert second.duplicate is True
        assert conversations["total"] == 1
        assert messages["total"] == 1
        assert messages["messages"][0]["status"] == MESSAGE_STATUS_PENDING
    finally:
        await ap.persistence_mgr.dispose()


async def test_generate_draft_updates_message_status_and_content():
    service, ap = await _create_service()
    try:
        await service.ingest_internal_event(_sample_payload())
        conversations = await service.list_conversations()
        messages = await service.list_messages(conversations["conversations"][0]["id"])
        message_id = messages["messages"][0]["id"]

        provider = SimpleNamespace(
            invoke_llm=AsyncMock(return_value=SimpleNamespace(content="Thanks, we will follow up shortly."))
        )
        ap.model_mgr.llm_models = [SimpleNamespace(provider=provider)]

        updated = await service.generate_draft(message_id)

        assert updated["status"] == MESSAGE_STATUS_DRAFT_READY
        assert updated["draft_text"] == "Thanks, we will follow up shortly."
        assert updated["draft_source"] == "ai"
    finally:
        await ap.persistence_mgr.dispose()


async def test_list_conversations_returns_searchable_summary_fields():
    service, ap = await _create_service()
    try:
        await service.ingest_internal_event(_sample_payload())

        result = await service.list_conversations(keyword="pricing")

        assert result["total"] == 1
        conversation = result["conversations"][0]
        assert conversation["connector_id"] == "wxwork-local"
        assert conversation["external_conversation_id"] == "S:100_200"
        assert conversation["latest_customer"] == "Customer A"
        assert conversation["latest_message_summary"] == "Need pricing details"
    finally:
        await ap.persistence_mgr.dispose()


async def test_process_skip_and_delete_message_update_state():
    service, ap = await _create_service()
    try:
        await service.ingest_internal_event(_sample_payload())
        conversations = await service.list_conversations()
        conversation_id = conversations["conversations"][0]["id"]
        messages = await service.list_messages(conversation_id)
        message_id = messages["messages"][0]["id"]

        processed = await service.process_message(message_id)
        assert processed["status"] == MESSAGE_STATUS_PROCESSED
        assert processed["attempt_count"] == 1

        skipped = await service.skip_message(message_id)
        assert skipped["status"] == MESSAGE_STATUS_SKIPPED

        await service.delete_message(message_id)
        remaining = await service.list_messages(conversation_id)
        assert remaining["total"] == 0
    finally:
        await ap.persistence_mgr.dispose()


async def test_batch_operations_require_message_ids():
    service, ap = await _create_service()
    try:
        with pytest.raises(ValueError, match="message_ids is required"):
            await service.batch_process([])
    finally:
        await ap.persistence_mgr.dispose()
