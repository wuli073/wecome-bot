from __future__ import annotations

import pytest

from langbot.pkg.database_mode.events import (
    DATABASE_MODE_EVENT_SENTINEL,
    DatabaseModeEvent,
    DatabaseModeEventBus,
    DatabaseModeEventType,
)


pytestmark = pytest.mark.asyncio


async def test_two_subscribers_receive_the_same_event():
    bus = DatabaseModeEventBus(queue_maxsize=4)
    first = bus.subscribe()
    second = bus.subscribe()
    event = DatabaseModeEvent(
        type=DatabaseModeEventType.MESSAGE_CREATED,
        conversation_id=1,
        message_id=2,
        occurred_at="2026-06-24T10:00:00+00:00",
    )

    await bus.publish(event)

    assert await first.queue.get() == event
    assert await second.queue.get() == event


async def test_overflow_coalesces_to_single_invalidated_event():
    bus = DatabaseModeEventBus(queue_maxsize=2)
    subscriber = bus.subscribe()

    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=1)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_DELETED, conversation_id=1, message_id=1)
    )

    drained = [subscriber.queue.get_nowait(), subscriber.queue.get_nowait()]

    assert drained[0].type == DatabaseModeEventType.MESSAGE_CREATED
    assert drained[1].type == DatabaseModeEventType.INVALIDATED


async def test_close_pushes_the_shutdown_sentinel():
    bus = DatabaseModeEventBus(queue_maxsize=1)
    subscriber = bus.subscribe()

    bus.close()

    assert subscriber.queue.get_nowait() is DATABASE_MODE_EVENT_SENTINEL
