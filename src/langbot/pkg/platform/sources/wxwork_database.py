from __future__ import annotations

import contextvars
import dataclasses
from contextlib import contextmanager
import typing

import pydantic

import langbot_plugin.api.definition.abstract.platform.adapter as abstract_platform_adapter
import langbot_plugin.api.definition.abstract.platform.event_logger as abstract_platform_logger
import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.message as platform_message


@dataclasses.dataclass
class DraftCapture:
    run_id: int | None
    query_id: int | None
    message_id: int | None
    context_visible: bool = False
    reply_called: bool = False
    reply_chunk_called: bool = False
    chunk_count: int = 0
    final_received: bool = False
    completed: bool = False
    segments: list[str] = dataclasses.field(default_factory=list)

    @property
    def text(self) -> str:
        return ''.join(segment for segment in self.segments if segment).strip()


class WXWorkDatabaseAdapter(abstract_platform_adapter.AbstractMessagePlatformAdapter):
    """Database-backed built-in adapter for compatibility-layer draft processing."""

    _draft_capture_var: typing.ClassVar[contextvars.ContextVar[DraftCapture | None]] = contextvars.ContextVar(
        'wxwork_database_draft_capture',
        default=None,
    )

    listeners: dict[
        typing.Type[platform_events.Event],
        typing.Callable[[platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], None],
    ] = pydantic.Field(default_factory=dict, exclude=True)

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, config: dict, logger: abstract_platform_logger.AbstractEventLogger, **kwargs):
        super().__init__(config=config, logger=logger, **kwargs)
        self.bot_account_id = str(config.get('connector_id') or 'wxwork-local')

    @contextmanager
    def capture_draft_output(self, *, run_id: int | None, query_id: int | None, message_id: int | None):
        capture = DraftCapture(run_id=run_id, query_id=query_id, message_id=message_id)
        token = self._draft_capture_var.set(capture)
        try:
            yield capture
        finally:
            self._draft_capture_var.reset(token)

    @classmethod
    def get_active_capture(cls) -> DraftCapture | None:
        return cls._draft_capture_var.get()

    @staticmethod
    def _message_to_text(message: platform_message.MessageChain | typing.Iterable[object] | str | object) -> str:
        if message is None:
            return ''
        if isinstance(message, str):
            return message
        if isinstance(message, platform_message.Plain):
            return message.text or ''
        if hasattr(message, 'text'):
            return str(getattr(message, 'text') or '')
        if isinstance(message, platform_message.MessageChain):
            parts = [WXWorkDatabaseAdapter._message_to_text(component) for component in message]
            return ''.join(part for part in parts if part)
        if isinstance(message, list):
            parts = [WXWorkDatabaseAdapter._message_to_text(component) for component in message]
            return ''.join(part for part in parts if part)
        return str(message)

    def _record_capture(
        self,
        *,
        message: platform_message.MessageChain,
        is_stream: bool,
        is_final: bool,
    ) -> str:
        capture = self.get_active_capture()
        content = self._message_to_text(message)
        if capture is None:
            return content

        capture.context_visible = True
        if is_stream:
            capture.reply_chunk_called = True
            capture.chunk_count += 1
        else:
            capture.reply_called = True

        if content:
            capture.segments.append(content)

        if is_final:
            capture.final_received = True
            capture.completed = True

        return content

    async def send_message(
        self,
        target_type: str,
        target_id: str,
        message: platform_message.MessageChain,
    ) -> dict:
        await self.logger.info(
            'wxwork_database adapter ignored active send request'
        )
        return {
            'status': 'unsupported',
            'reason': 'wxwork_database does not support active sending',
            'target_type': target_type,
            'target_id': target_id,
        }

    async def reply_message(
        self,
        message_source: platform_events.MessageEvent,
        message: platform_message.MessageChain,
        quote_origin: bool = False,
    ) -> dict:
        content = self._record_capture(message=message, is_stream=False, is_final=True)
        return {
            'status': 'draft_ready',
            'content': content,
            'quote_origin': quote_origin,
            'is_final': True,
        }

    async def reply_message_chunk(
        self,
        message_source: platform_events.MessageEvent,
        bot_message,
        message: platform_message.MessageChain,
        quote_origin: bool = False,
        is_final: bool = False,
    ) -> dict:
        content = self._record_capture(message=message, is_stream=True, is_final=bool(is_final))
        return {
            'status': 'draft_ready',
            'content': content,
            'quote_origin': quote_origin,
            'is_final': bool(is_final),
        }

    def register_listener(
        self,
        event_type: typing.Type[platform_events.Event],
        callback: typing.Callable[
            [platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], None
        ],
    ):
        self.listeners[event_type] = callback

    def unregister_listener(
        self,
        event_type: typing.Type[platform_events.Event],
        callback: typing.Callable[
            [platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], None
        ],
    ):
        self.listeners.pop(event_type, None)

    async def run_async(self):
        return None

    async def kill(self) -> bool:
        return True
