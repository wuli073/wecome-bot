from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import sqlalchemy

from langbot.pkg.api.http.service.bot import BotService
from langbot.pkg.entity.persistence import bot as persistence_bot
from langbot.pkg.entity.persistence import database_mode as persistence_database_mode
from langbot.pkg.platform.botmgr import PlatformManager
from tests.unit_tests.api.http.service.test_bot_service import _PersistenceManager


pytestmark = pytest.mark.asyncio


class _Result:
    def __init__(self, bots):
        self._bots = bots

    def all(self):
        return self._bots


async def test_load_bots_from_db_backfills_wxwork_database_bindings_before_loading():
    wxwork_bot = SimpleNamespace(
        uuid='wxwork-bot',
        adapter='wxwork_database',
        adapter_config={'connector_id': 'wxwork-local', 'auto_generate_draft': True},
        enable=True,
    )
    telegram_bot = SimpleNamespace(
        uuid='telegram-bot',
        adapter='telegram',
        adapter_config={},
        enable=False,
    )
    call_log = []

    async def _record_binding(**kwargs):
        call_log.append(('binding', kwargs['bot_uuid']))

    async def _record_load(bot):
        call_log.append(('load', bot.uuid))

    ap = SimpleNamespace(
        logger=SimpleNamespace(info=Mock(), warning=Mock(), error=Mock()),
        persistence_mgr=SimpleNamespace(execute_async=AsyncMock(return_value=_Result([wxwork_bot, telegram_bot]))),
        bot_service=SimpleNamespace(_ensure_wxwork_database_binding=AsyncMock(side_effect=_record_binding)),
    )
    manager = PlatformManager(ap=ap)
    manager.load_bot = AsyncMock(side_effect=_record_load)

    await manager.load_bots_from_db()

    ap.bot_service._ensure_wxwork_database_binding.assert_awaited_once_with(
        bot_uuid='wxwork-bot',
        adapter_config=wxwork_bot.adapter_config,
        bot_enabled=True,
    )
    assert call_log == [('binding', 'wxwork-bot'), ('load', 'wxwork-bot'), ('load', 'telegram-bot')]


async def test_load_bots_from_db_repeated_backfill_keeps_single_binding():
    persistence_mgr = _PersistenceManager()
    await persistence_mgr.initialize()
    async with persistence_mgr.sessionmaker() as session:
        await session.execute(
            sqlalchemy.insert(persistence_bot.Bot).values(
                {
                    'uuid': 'wxwork-bot',
                    'name': 'WXWork Bot',
                    'description': 'desc',
                    'adapter': 'wxwork_database',
                    'adapter_config': {'connector_id': 'wxwork-local', 'auto_generate_draft': True},
                    'enable': True,
                    'pipeline_routing_rules': [],
                }
            )
        )
        await session.commit()

    ap = SimpleNamespace(
        logger=SimpleNamespace(info=Mock(), warning=Mock(), error=Mock()),
        persistence_mgr=persistence_mgr,
    )
    ap.platform_mgr = PlatformManager(ap=ap)
    ap.bot_service = BotService(ap)
    ap.platform_mgr.load_bot = AsyncMock(return_value=SimpleNamespace(enable=True, run=AsyncMock()))

    await ap.platform_mgr.load_bots_from_db()
    await ap.platform_mgr.load_bots_from_db()

    binding_count = (
        await persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.BotChannelBinding)
        )
    ).scalar_one()
    channel_account_count = (
        await persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(persistence_database_mode.ChannelAccount)
        )
    ).scalar_one()

    assert binding_count == 1
    assert channel_account_count == 1
