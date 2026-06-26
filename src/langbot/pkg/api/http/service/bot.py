from __future__ import annotations

import datetime
import uuid
import sqlalchemy
import typing
from sqlalchemy.exc import IntegrityError

from ....core import app
from ....entity.persistence import database_mode as persistence_database_mode
from ....entity.persistence import bot as persistence_bot
from ....entity.persistence import pipeline as persistence_pipeline


class BotService:
    """Bot service"""

    ap: app.Application

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap

    @staticmethod
    def _utcnow_iso() -> str:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    @classmethod
    def _normalize_adapter_config(
        cls,
        adapter: str,
        adapter_config: dict | None,
        *,
        enabled: bool,
        previous_adapter_config: dict | None = None,
        previous_enabled: bool | None = None,
    ) -> dict:
        config = dict(adapter_config or {})
        if adapter != 'wxwork_database':
            return config

        config['connector_id'] = 'wxwork-local'
        config['auto_generate_draft'] = bool(config.get('auto_generate_draft', False))

        previous_processing_since = None
        if isinstance(previous_adapter_config, dict):
            previous_processing_since = previous_adapter_config.get('processing_since')

        if enabled and not previous_enabled:
            config['processing_since'] = cls._utcnow_iso()
        elif previous_processing_since:
            config['processing_since'] = previous_processing_since

        return config

    @staticmethod
    def _parse_optional_utc_datetime(value: object) -> datetime.datetime | None:
        if isinstance(value, datetime.datetime):
            parsed = value
        else:
            text = str(value or '').strip()
            if not text:
                return None
            normalized = text[:-1] + '+00:00' if text.endswith('Z') else text
            try:
                parsed = datetime.datetime.fromisoformat(normalized)
            except ValueError:
                return None

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _utcnow_dt() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    async def _validate_wxwork_database_enable_conflict(
        self,
        *,
        adapter: str,
        enabled: bool,
        adapter_config: dict | None,
        current_bot_uuid: str | None = None,
    ) -> None:
        if adapter != 'wxwork_database' or not enabled:
            return

        connector_id = str((adapter_config or {}).get('connector_id') or 'wxwork-local').strip() or 'wxwork-local'
        bots = await self.get_bots()
        for bot in bots:
            if bot.get('uuid') == current_bot_uuid:
                continue
            if bot.get('adapter') != 'wxwork_database':
                continue
            if not bool(bot.get('enable', False)):
                continue
            existing_connector_id = str((bot.get('adapter_config') or {}).get('connector_id') or '').strip()
            if existing_connector_id == connector_id:
                raise ValueError(
                    f'Only one enabled wxwork_database bot is allowed for connector_id={connector_id}'
                )

    async def _ensure_wxwork_database_binding(
        self,
        *,
        bot_uuid: str,
        adapter_config: dict,
        bot_enabled: bool,
    ) -> None:
        connector_id = str(adapter_config.get('connector_id') or 'wxwork-local').strip() or 'wxwork-local'
        auto_generate_draft = bool(adapter_config.get('auto_generate_draft', False))
        processing_since = self._parse_optional_utc_datetime(adapter_config.get('processing_since'))

        channel_account = await self._get_wxwork_database_channel_account(connector_id)
        if channel_account is None:
            try:
                await self.ap.persistence_mgr.execute_async(self._build_channel_account_insert(connector_id))
            except IntegrityError:
                pass
            channel_account = await self._get_wxwork_database_channel_account(connector_id)

        if channel_account is None:
            raise RuntimeError('Failed to ensure wxwork database channel account')

        if not channel_account.enabled or channel_account.display_name != 'WXWork Database':
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_database_mode.ChannelAccount)
                .where(persistence_database_mode.ChannelAccount.id == channel_account.id)
                .values(
                    {
                        'enabled': True,
                        'display_name': 'WXWork Database',
                    }
                )
            )

        binding = await self._get_wxwork_database_binding(bot_uuid, int(channel_account.id))
        if bot_enabled:
            effective_from = processing_since or (binding.effective_from if binding is not None else None) or self._utcnow_dt()
        else:
            effective_from = binding.effective_from if binding is not None else None

        binding_values = {
            'enabled': bot_enabled,
            'effective_from': effective_from,
            'auto_generate_draft': auto_generate_draft,
        }
        if binding is None:
            try:
                await self.ap.persistence_mgr.execute_async(
                    self._build_binding_insert(bot_uuid, int(channel_account.id), binding_values)
                )
            except IntegrityError:
                pass
            binding = await self._get_wxwork_database_binding(bot_uuid, int(channel_account.id))

        if binding is None:
            raise RuntimeError('Failed to ensure wxwork database binding')

        if (
            bool(binding.enabled) != bot_enabled
            or binding.auto_generate_draft != auto_generate_draft
            or (
                bot_enabled
                and processing_since is not None
                and binding.effective_from != processing_since
            )
        ):
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_database_mode.BotChannelBinding)
                .where(persistence_database_mode.BotChannelBinding.id == binding.id)
                .values(binding_values)
            )

    async def _disable_wxwork_database_bindings(self, bot_uuid: str) -> None:
        bindings_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.BotChannelBinding.id).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid
            )
        )
        binding_ids = bindings_result.scalars().all()
        for binding_id in binding_ids:
            await self.ap.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_database_mode.BotChannelBinding)
                .where(persistence_database_mode.BotChannelBinding.id == binding_id)
                .values(
                    {
                        'enabled': False,
                    }
                )
            )

    async def _delete_wxwork_database_bindings(self, bot_uuid: str) -> None:
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_database_mode.BotChannelBinding).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid
            )
        )

    @staticmethod
    def _build_channel_account_insert(connector_id: str):
        return sqlalchemy.insert(persistence_database_mode.ChannelAccount).values(
            {
                'connector_id': connector_id,
                'channel_type': 'wxwork_database',
                'external_account_id': connector_id,
                'display_name': 'WXWork Database',
                'enabled': True,
                'channel_metadata': {},
            }
        )

    @staticmethod
    def _build_binding_insert(bot_uuid: str, channel_account_id: int, binding_values: dict):
        return sqlalchemy.insert(persistence_database_mode.BotChannelBinding).values(
            {
                'bot_uuid': bot_uuid,
                'channel_account_id': channel_account_id,
                **binding_values,
            }
        )

    async def _get_wxwork_database_channel_account(self, connector_id: str):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.ChannelAccount.id,
                persistence_database_mode.ChannelAccount.connector_id,
                persistence_database_mode.ChannelAccount.channel_type,
                persistence_database_mode.ChannelAccount.external_account_id,
                persistence_database_mode.ChannelAccount.display_name,
                persistence_database_mode.ChannelAccount.enabled,
                persistence_database_mode.ChannelAccount.channel_metadata.label('channel_metadata'),
                persistence_database_mode.ChannelAccount.created_at,
                persistence_database_mode.ChannelAccount.updated_at,
            ).where(
                persistence_database_mode.ChannelAccount.connector_id == connector_id,
                persistence_database_mode.ChannelAccount.channel_type == 'wxwork_database',
                persistence_database_mode.ChannelAccount.external_account_id == connector_id,
            )
        )
        return result.first()

    async def _get_wxwork_database_binding(self, bot_uuid: str, channel_account_id: int):
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_database_mode.BotChannelBinding.id,
                persistence_database_mode.BotChannelBinding.bot_uuid,
                persistence_database_mode.BotChannelBinding.channel_account_id,
                persistence_database_mode.BotChannelBinding.enabled,
                persistence_database_mode.BotChannelBinding.effective_from,
                persistence_database_mode.BotChannelBinding.auto_generate_draft,
                persistence_database_mode.BotChannelBinding.created_at,
                persistence_database_mode.BotChannelBinding.updated_at,
            ).where(
                persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid,
                persistence_database_mode.BotChannelBinding.channel_account_id == channel_account_id,
            )
        )
        return result.first()

    async def get_bots(self, include_secret: bool = True) -> list[dict]:
        """获取所有机器人"""
        result = await self.ap.persistence_mgr.execute_async(sqlalchemy.select(persistence_bot.Bot))

        bots = result.all()

        masked_columns = []
        if not include_secret:
            masked_columns = ['adapter_config']

        return [self.ap.persistence_mgr.serialize_model(persistence_bot.Bot, bot, masked_columns) for bot in bots]

    async def get_bot(self, bot_uuid: str, include_secret: bool = True) -> dict | None:
        """获取机器人"""
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_bot.Bot).where(persistence_bot.Bot.uuid == bot_uuid)
        )

        bot = result.first()

        if bot is None:
            return None

        masked_columns = []
        if not include_secret:
            masked_columns = ['adapter_config']

        return self.ap.persistence_mgr.serialize_model(persistence_bot.Bot, bot, masked_columns)

    async def get_runtime_bot_info(self, bot_uuid: str, include_secret: bool = True) -> dict:
        """获取机器人运行时信息"""
        persistence_bot = await self.get_bot(bot_uuid, include_secret)
        if persistence_bot is None:
            raise Exception('Bot not found')

        adapter_runtime_values = {}

        runtime_bot = await self.ap.platform_mgr.get_bot_by_uuid(bot_uuid)
        if runtime_bot is not None:
            adapter_runtime_values['bot_account_id'] = runtime_bot.adapter.bot_account_id

        # Webhook URL for unified webhook adapters (independent of bot running state)
        if persistence_bot['adapter'] in [
            'wecom',
            'wecombot',
            'officialaccount',
            'qqofficial',
            'slack',
            'wecomcs',
            'LINE',
            'lark',
        ]:
            webhook_prefix = self.ap.instance_config.data['api'].get('webhook_prefix', 'http://127.0.0.1:5300')
            extra_webhook_prefix = self.ap.instance_config.data['api'].get('extra_webhook_prefix', '')
            webhook_url = f'/bots/{bot_uuid}'
            adapter_runtime_values['webhook_url'] = webhook_url
            adapter_runtime_values['webhook_full_url'] = f'{webhook_prefix}{webhook_url}'
            adapter_runtime_values['extra_webhook_full_url'] = (
                f'{extra_webhook_prefix}{webhook_url}' if extra_webhook_prefix else ''
            )
        else:
            adapter_runtime_values['webhook_url'] = None
            adapter_runtime_values['webhook_full_url'] = None
            adapter_runtime_values['extra_webhook_full_url'] = None

        persistence_bot['adapter_runtime_values'] = adapter_runtime_values

        return persistence_bot

    async def create_bot(self, bot_data: dict) -> str:
        """Create bot"""
        # Check limitation
        limitation = self.ap.instance_config.data.get('system', {}).get('limitation', {})
        max_bots = limitation.get('max_bots', -1)
        if max_bots >= 0:
            existing_bots = await self.get_bots()
            if len(existing_bots) >= max_bots:
                raise ValueError(f'Maximum number of bots ({max_bots}) reached')

        # TODO: 检查配置信息格式
        bot_data['adapter_config'] = self._normalize_adapter_config(
            bot_data.get('adapter', ''),
            bot_data.get('adapter_config'),
            enabled=bool(bot_data.get('enable', False)),
        )
        await self._validate_wxwork_database_enable_conflict(
            adapter=bot_data.get('adapter', ''),
            enabled=bool(bot_data.get('enable', False)),
            adapter_config=bot_data.get('adapter_config'),
        )
        bot_data['uuid'] = str(uuid.uuid4())

        # bind the most recently updated pipeline if any exist
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_pipeline.LegacyPipeline)
            .order_by(persistence_pipeline.LegacyPipeline.updated_at.desc())
            .limit(1)
        )
        pipeline = result.first()
        if pipeline is not None:
            bot_data['use_pipeline_uuid'] = pipeline.uuid
            bot_data['use_pipeline_name'] = pipeline.name

        await self.ap.persistence_mgr.execute_async(sqlalchemy.insert(persistence_bot.Bot).values(bot_data))

        if bot_data.get('adapter') == 'wxwork_database':
            await self._ensure_wxwork_database_binding(
                bot_uuid=bot_data['uuid'],
                adapter_config=bot_data.get('adapter_config') or {},
                bot_enabled=bool(bot_data.get('enable', False)),
            )

        bot = await self.get_bot(bot_data['uuid'])

        await self.ap.platform_mgr.load_bot(bot)

        return bot['uuid']

    async def update_bot(self, bot_uuid: str, bot_data: dict) -> None:
        """Update bot"""
        update_data = bot_data.copy()
        existing_bot = await self.get_bot(bot_uuid)
        if existing_bot is None:
            raise Exception('Bot not found')

        if 'uuid' in update_data:
            del update_data['uuid']

        effective_adapter = update_data.get('adapter', existing_bot.get('adapter', ''))
        effective_enable = bool(update_data.get('enable', existing_bot.get('enable', False)))
        if effective_adapter == 'wxwork_database' or 'adapter_config' in update_data:
            update_data['adapter_config'] = self._normalize_adapter_config(
                effective_adapter,
                update_data.get('adapter_config', existing_bot.get('adapter_config')),
                enabled=effective_enable,
                previous_adapter_config=existing_bot.get('adapter_config'),
                previous_enabled=bool(existing_bot.get('enable', False)),
            )
        await self._validate_wxwork_database_enable_conflict(
            adapter=effective_adapter,
            enabled=effective_enable,
            adapter_config=update_data.get('adapter_config', existing_bot.get('adapter_config')),
            current_bot_uuid=bot_uuid,
        )

        # set use_pipeline_name
        if 'use_pipeline_uuid' in update_data:
            result = await self.ap.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_pipeline.LegacyPipeline).where(
                    persistence_pipeline.LegacyPipeline.uuid == update_data['use_pipeline_uuid']
                )
            )
            pipeline = result.first()
            if pipeline is not None:
                update_data['use_pipeline_name'] = pipeline.name
            else:
                raise Exception('Pipeline not found')

        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_bot.Bot).values(update_data).where(persistence_bot.Bot.uuid == bot_uuid)
        )

        if effective_adapter == 'wxwork_database':
            await self._ensure_wxwork_database_binding(
                bot_uuid=bot_uuid,
                adapter_config=update_data.get('adapter_config', existing_bot.get('adapter_config') or {}),
                bot_enabled=effective_enable,
            )
        elif existing_bot.get('adapter') == 'wxwork_database':
            await self._disable_wxwork_database_bindings(bot_uuid)

        await self.ap.platform_mgr.remove_bot(bot_uuid)

        # select from db
        bot = await self.get_bot(bot_uuid)

        runtime_bot = await self.ap.platform_mgr.load_bot(bot)

        if runtime_bot.enable:
            await runtime_bot.run()

        # update all conversation that use this bot
        for session in self.ap.sess_mgr.session_list:
            if session.using_conversation is not None and session.using_conversation.bot_uuid == bot_uuid:
                session.using_conversation = None

    async def delete_bot(self, bot_uuid: str) -> None:
        """Delete bot"""
        await self._delete_wxwork_database_bindings(bot_uuid)
        await self.ap.platform_mgr.remove_bot(bot_uuid)
        await self.ap.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_bot.Bot).where(persistence_bot.Bot.uuid == bot_uuid)
        )

    async def list_event_logs(
        self, bot_uuid: str, from_index: int, max_count: int
    ) -> typing.Tuple[list[dict], int, int, int]:
        runtime_bot = await self.ap.platform_mgr.get_bot_by_uuid(bot_uuid)
        if runtime_bot is None:
            raise Exception('Bot not found')

        logs, total_count = await runtime_bot.logger.get_logs(from_index, max_count)

        return [log.to_json() for log in logs], total_count

    async def send_message(self, bot_uuid: str, target_type: str, target_id: str, message_chain_data: dict) -> None:
        """Send message to a specific target via bot

        Args:
            bot_uuid: The UUID of the bot
            target_type: The type of the target, can be "group", "person"
            target_id: The ID of the target
            message_chain_data: The message chain data in dict format
        """
        # Import here to avoid circular imports
        import langbot_plugin.api.entities.builtin.platform.message as platform_message

        # Get runtime bot
        runtime_bot = await self.ap.platform_mgr.get_bot_by_uuid(bot_uuid)
        if runtime_bot is None:
            raise Exception(f'Bot not found: {bot_uuid}')

        # Validate and convert message chain
        try:
            message_chain = platform_message.MessageChain.model_validate(message_chain_data)
        except Exception as e:
            raise Exception(f'Invalid message_chain format: {str(e)}')

        # Send message via adapter
        await runtime_bot.adapter.send_message(target_type, str(target_id), message_chain)
