from __future__ import annotations

import pytest

from langbot.pkg.database_mode.events import (
    DATABASE_MODE_EVENT_SENTINEL,
    DatabaseModeEvent,
    DatabaseModeEventBus,
    DatabaseModeEventType,
    serialize_sse_event,
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

    drained = [subscriber.queue.get_nowait()]

    assert drained[0].type == DatabaseModeEventType.INVALIDATED
    assert subscriber.queue.empty()


async def test_overflow_delivers_invalidated_promptly_for_larger_queues():
    bus = DatabaseModeEventBus(queue_maxsize=4)
    subscriber = bus.subscribe()

    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=2)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=3)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=4)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_DELETED, conversation_id=1, message_id=5)
    )
    assert subscriber.queue.qsize() == 1
    assert subscriber.queue.get_nowait().type == DatabaseModeEventType.INVALIDATED
    assert subscriber.queue.empty()

    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=6)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=7)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=8)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=9)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_DELETED, conversation_id=1, message_id=10)
    )

    assert subscriber.queue.qsize() == 1
    assert subscriber.queue.get_nowait().type == DatabaseModeEventType.INVALIDATED
    assert subscriber.queue.empty()


async def test_invalidated_marker_stays_terminal_until_drained():
    bus = DatabaseModeEventBus(queue_maxsize=2)
    subscriber = bus.subscribe()

    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=2)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_DELETED, conversation_id=1, message_id=3)
    )

    assert subscriber.queue.qsize() == 1
    assert subscriber.queue._queue[0].type == DatabaseModeEventType.INVALIDATED

    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=4)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=5)
    )
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_DELETED, conversation_id=1, message_id=6)
    )

    assert subscriber.queue.qsize() == 1
    assert subscriber.queue.get_nowait().type == DatabaseModeEventType.INVALIDATED
    assert subscriber.queue.empty()


async def test_unsubscribe_stops_future_delivery():
    bus = DatabaseModeEventBus(queue_maxsize=2)
    subscriber = bus.subscribe()

    bus.unsubscribe(subscriber.subscriber_id)
    await bus.publish(DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1))

    assert subscriber.queue.empty()


async def test_close_replaces_full_queue_with_shutdown_sentinel():
    bus = DatabaseModeEventBus(queue_maxsize=1)
    subscriber = bus.subscribe()

    await bus.publish(DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1))

    bus.close()

    assert subscriber.queue.get_nowait() is DATABASE_MODE_EVENT_SENTINEL


async def test_close_pushes_the_shutdown_sentinel():
    bus = DatabaseModeEventBus(queue_maxsize=1)
    subscriber = bus.subscribe()

    bus.close()

    assert subscriber.queue.get_nowait() is DATABASE_MODE_EVENT_SENTINEL


async def test_publish_after_close_does_not_replace_shutdown_sentinel():
    bus = DatabaseModeEventBus(queue_maxsize=1)
    subscriber = bus.subscribe()

    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_CREATED, conversation_id=1, message_id=1)
    )
    bus.close()
    await bus.publish(
        DatabaseModeEvent(type=DatabaseModeEventType.MESSAGE_UPDATED, conversation_id=1, message_id=1)
    )

    assert subscriber.queue.get_nowait() is DATABASE_MODE_EVENT_SENTINEL
    assert subscriber.queue.empty()


async def test_serialize_sse_event_emits_event_and_json_payload():
    event = DatabaseModeEvent(
        type=DatabaseModeEventType.MESSAGE_CREATED,
        conversation_id=1,
        message_id=2,
        occurred_at='2026-06-24T10:00:00+00:00',
        event_id='evt-1',
    )

    payload = serialize_sse_event(event)

    assert payload == (
        'event: database-message-created\n'
        'data: {"type": "database-message-created", "conversation_id": 1, "message_id": 2, '
        '"occurred_at": "2026-06-24T10:00:00+00:00", "event_id": "evt-1"}\n\n'
    )
