from __future__ import annotations

import asyncio
import dataclasses
import datetime
import enum
import json
import uuid


DATABASE_MODE_EVENT_SENTINEL = object()


class DatabaseModeEventType(str, enum.Enum):
    MESSAGE_CREATED = 'database-message-created'
    MESSAGE_UPDATED = 'database-message-updated'
    MESSAGE_DELETED = 'database-message-deleted'
    CONVERSATION_UPDATED = 'database-conversation-updated'
    INVALIDATED = 'database-mode-invalidated'
    READY = 'ready'


@dataclasses.dataclass(slots=True)
class DatabaseModeEvent:
    type: DatabaseModeEventType
    conversation_id: int | None = None
    message_id: int | None = None
    occurred_at: str | None = None
    event_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict | None = None


@dataclasses.dataclass(slots=True)
class DatabaseModeSubscriber:
    subscriber_id: str
    queue: asyncio.Queue


class DatabaseModeEventBus:
    def __init__(self, queue_maxsize: int = 100) -> None:
        self._queue_maxsize = queue_maxsize
        self._subscribers: dict[str, DatabaseModeSubscriber] = {}
        self._closed = False

    def subscribe(self) -> DatabaseModeSubscriber:
        if self._closed:
            subscriber = DatabaseModeSubscriber(
                subscriber_id=str(uuid.uuid4()),
                queue=asyncio.Queue(maxsize=self._queue_maxsize),
            )
            subscriber.queue.put_nowait(DATABASE_MODE_EVENT_SENTINEL)
            return subscriber
        subscriber = DatabaseModeSubscriber(
            subscriber_id=str(uuid.uuid4()),
            queue=asyncio.Queue(maxsize=self._queue_maxsize),
        )
        self._subscribers[subscriber.subscriber_id] = subscriber
        return subscriber

    def unsubscribe(self, subscriber_id: str) -> None:
        self._subscribers.pop(subscriber_id, None)

    async def publish(self, event: DatabaseModeEvent) -> None:
        if self._closed:
            return
        for subscriber in list(self._subscribers.values()):
            self._publish_to_subscriber(subscriber, event)

    def _publish_to_subscriber(self, subscriber: DatabaseModeSubscriber, event: DatabaseModeEvent) -> None:
        if self._queue_has_shutdown_sentinel(subscriber):
            return
        if self._queue_has_invalidated_marker(subscriber):
            return

        try:
            subscriber.queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        invalidated = DatabaseModeEvent(
            type=DatabaseModeEventType.INVALIDATED,
            occurred_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        while True:
            try:
                subscriber.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        subscriber.queue.put_nowait(invalidated)

    @staticmethod
    def _queue_has_invalidated_marker(subscriber: DatabaseModeSubscriber) -> bool:
        queued_items = getattr(subscriber.queue, '_queue', ())
        return any(
            isinstance(item, DatabaseModeEvent) and item.type == DatabaseModeEventType.INVALIDATED
            for item in queued_items
        )

    @staticmethod
    def _queue_has_shutdown_sentinel(subscriber: DatabaseModeSubscriber) -> bool:
        queued_items = getattr(subscriber.queue, '_queue', ())
        return any(item is DATABASE_MODE_EVENT_SENTINEL for item in queued_items)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for subscriber in list(self._subscribers.values()):
            try:
                subscriber.queue.put_nowait(DATABASE_MODE_EVENT_SENTINEL)
            except asyncio.QueueFull:
                subscriber.queue.get_nowait()
                subscriber.queue.put_nowait(DATABASE_MODE_EVENT_SENTINEL)

        self._subscribers.clear()


def serialize_sse_event(event: DatabaseModeEvent) -> str:
    return (
        f'event: {event.type.value}\n'
        f'data: {json.dumps(dataclasses.asdict(event), ensure_ascii=True)}\n\n'
    )
