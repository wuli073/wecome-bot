from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import langbot_plugin.api.definition.abstract.platform.event_logger as abstract_platform_logger
import langbot_plugin.api.entities.builtin.platform.message as platform_message
from langbot.pkg.discover.engine import ComponentDiscoveryEngine
from langbot.pkg.platform.sources.wxwork_database import WXWorkDatabaseAdapter


class DummyEventLogger(abstract_platform_logger.AbstractEventLogger):
    def __init__(self) -> None:
        self.info_mock = AsyncMock()
        self.debug_mock = AsyncMock()
        self.warning_mock = AsyncMock()
        self.error_mock = AsyncMock()

    async def info(self, text, images=None, message_session_id=None, no_throw=True):
        await self.info_mock(text, images=images, message_session_id=message_session_id, no_throw=no_throw)

    async def debug(self, text, images=None, message_session_id=None, no_throw=True):
        await self.debug_mock(text, images=images, message_session_id=message_session_id, no_throw=no_throw)

    async def warning(self, text, images=None, message_session_id=None, no_throw=True):
        await self.warning_mock(text, images=images, message_session_id=message_session_id, no_throw=no_throw)

    async def error(self, text, images=None, message_session_id=None, no_throw=True):
        await self.error_mock(text, images=images, message_session_id=message_session_id, no_throw=no_throw)


def _build_message_chain(text: str = 'draft text') -> platform_message.MessageChain:
    return platform_message.MessageChain([platform_message.Plain(text=text)])


def test_wxwork_database_manifest_is_discoverable():
    ap = SimpleNamespace(logger=Mock(debug=Mock()))
    discover = ComponentDiscoveryEngine(ap)

    component = discover.load_component_manifest('pkg/platform/sources/wxwork_database.yaml', no_save=True)

    assert component is not None
    assert component.metadata.name == 'wxwork_database'
    assert component.metadata.label.en_US == 'WeCom Database'
    assert component.execution.python.attr == 'WXWorkDatabaseAdapter'


@pytest.mark.asyncio
async def test_wxwork_database_adapter_send_message_never_sends_real_message():
    logger = DummyEventLogger()
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=logger)

    result = await adapter.send_message('person', 'target-1', _build_message_chain())

    assert result['status'] == 'unsupported'
    assert 'does not support active sending' in result['reason']
    logger.info_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_wxwork_database_adapter_reply_message_returns_final_draft_payload():
    logger = DummyEventLogger()
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=logger)
    source = SimpleNamespace()

    result = await adapter.reply_message(source, _build_message_chain('pipeline draft'))

    assert result['status'] == 'draft_ready'
    assert result['content'] == 'pipeline draft'
    assert result['is_final'] is True


@pytest.mark.asyncio
async def test_wxwork_database_adapter_captures_non_stream_reply_without_real_send():
    logger = DummyEventLogger()
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=logger)
    source = SimpleNamespace()

    with adapter.capture_draft_output(run_id=1, query_id=2, message_id=3) as capture:
        result = await adapter.reply_message(source, _build_message_chain('captured draft'))

    assert result['status'] == 'draft_ready'
    assert result['content'] == 'captured draft'
    assert capture.completed is True
    assert capture.reply_called is True
    assert capture.reply_chunk_called is False
    assert capture.chunk_count == 0
    assert capture.final_received is True
    assert capture.text == 'captured draft'


@pytest.mark.asyncio
async def test_wxwork_database_adapter_captures_stream_chunks_until_final():
    logger = DummyEventLogger()
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=logger)
    source = SimpleNamespace()

    with adapter.capture_draft_output(run_id=11, query_id=22, message_id=33) as capture:
        first = await adapter.reply_message_chunk(
            source,
            bot_message={'id': 'resp-1'},
            message=_build_message_chain('chunk-1'),
            is_final=False,
        )
        second = await adapter.reply_message_chunk(
            source,
            bot_message={'id': 'resp-1'},
            message=_build_message_chain('chunk-2'),
            is_final=False,
        )
        final = await adapter.reply_message_chunk(
            source,
            bot_message={'id': 'resp-1'},
            message=_build_message_chain('chunk-3'),
            is_final=True,
        )

    assert first['is_final'] is False
    assert second['is_final'] is False
    assert final['is_final'] is True
    assert capture.reply_called is False
    assert capture.reply_chunk_called is True
    assert capture.chunk_count == 3
    assert capture.final_received is True
    assert capture.completed is True
    assert capture.text == 'chunk-1chunk-2chunk-3'


@pytest.mark.asyncio
async def test_wxwork_database_adapter_capture_is_isolated_per_concurrent_task():
    logger = DummyEventLogger()
    adapter = WXWorkDatabaseAdapter(config={'connector_id': 'wxwork-local'}, logger=logger)
    source = SimpleNamespace()

    async def _run_capture(run_id: int, text: str) -> str:
        with adapter.capture_draft_output(run_id=run_id, query_id=run_id, message_id=run_id) as capture:
            await asyncio.sleep(0)
            await adapter.reply_message(source, _build_message_chain(text))
            await asyncio.sleep(0)
            return capture.text

    left, right = await asyncio.gather(
        _run_capture(101, 'left draft'),
        _run_capture(202, 'right draft'),
    )

    assert left == 'left draft'
    assert right == 'right draft'
