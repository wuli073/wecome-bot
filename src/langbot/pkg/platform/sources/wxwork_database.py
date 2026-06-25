from __future__ import annotations

import typing

import pydantic

import langbot_plugin.api.definition.abstract.platform.adapter as abstract_platform_adapter
import langbot_plugin.api.definition.abstract.platform.event_logger as abstract_platform_logger
import langbot_plugin.api.entities.builtin.platform.events as platform_events
import langbot_plugin.api.entities.builtin.platform.message as platform_message


class WXWorkDatabaseAdapter(abstract_platform_adapter.AbstractMessagePlatformAdapter):
    """Database-backed built-in adapter for compatibility-layer draft processing."""

    listeners: dict[
        typing.Type[platform_events.Event],
        typing.Callable[[platform_events.Event, abstract_platform_adapter.AbstractMessagePlatformAdapter], None],
    ] = pydantic.Field(default_factory=dict, exclude=True)

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, config: dict, logger: abstract_platform_logger.AbstractEventLogger, **kwargs):
        super().__init__(config=config, logger=logger, **kwargs)
        self.bot_account_id = str(config.get('connector_id') or 'wxwork-local')

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
        return {
            'status': 'draft_ready',
            'content': str(message),
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
        return {
            'status': 'draft_ready',
            'content': str(message),
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
