from __future__ import annotations

import re
from typing import Any

import sqlalchemy
from sqlalchemy.exc import IntegrityError

from .errors import (
    BROADCAST_GROUP_NAME_DUPLICATE,
    BROADCAST_GROUP_NAME_NOT_FOUND,
    BROADCAST_GROUP_RULE_DUPLICATE,
    BROADCAST_GROUP_RULE_NOT_FOUND,
    BROADCAST_GROUP_RULE_REGEX_INVALID,
    BROADCAST_SCOPE_REQUIRED,
    BROADCAST_TEMPLATE_CONTENT_REQUIRED,
    BROADCAST_TEMPLATE_NAME_DUPLICATE,
    BROADCAST_TEMPLATE_NOT_FOUND,
    BROADCAST_VARIABLE_PROFILE_INVALID,
    TEMPLATE_RENDER_INPUT_INVALID,
    BroadcastError,
)
from .repository import BroadcastRepository
from .schemas import VALID_MATCH_TYPES, VALID_MERGE_MODES
from .template_engine import extract_variables, render_template as safe_render_template


class BroadcastService:
    def __init__(self, ap) -> None:
        self.ap = ap
        self.repository = BroadcastRepository(ap.persistence_mgr)

    async def validate_scope(self, scope: dict[str, Any]) -> dict[str, str]:
        bot_uuid = str(scope.get('bot_uuid') or '').strip()
        connector_id = str(scope.get('connector_id') or '').strip()
        if not bot_uuid or not connector_id:
            raise BroadcastError(BROADCAST_SCOPE_REQUIRED)

        bot = await self.ap.bot_service.get_bot(bot_uuid, include_secret=False)
        if bot is None or bot.get('adapter') != 'wxwork_database':
            raise BroadcastError(BROADCAST_SCOPE_REQUIRED)

        actual_connector_id = await self._get_bound_connector_id(bot_uuid)
        if actual_connector_id != connector_id:
            raise BroadcastError(BROADCAST_SCOPE_REQUIRED)
        return {
            'bot_uuid': bot_uuid,
            'connector_id': connector_id,
        }

    async def list_templates(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        rows = await self.repository.list_templates(**validated_scope)
        return [self._serialize_template(row) for row in rows]

    async def create_template(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        normalized = self._normalize_template_payload(payload)
        try:
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                template_id = await self.repository.create_template(
                    conn,
                    {
                        **validated_scope,
                        **normalized,
                    },
                )
        except IntegrityError as exc:
            raise self._map_integrity_error(exc) from exc
        template = await self.repository.get_template(template_id, **validated_scope)
        return self._serialize_template(template)

    async def update_template(
        self,
        template_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        normalized = self._normalize_template_payload(payload)
        try:
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                updated = await self.repository.update_template(
                    template_id,
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates=normalized,
                    conn=conn,
                )
        except IntegrityError as exc:
            raise self._map_integrity_error(exc) from exc
        if updated is None:
            raise BroadcastError(BROADCAST_TEMPLATE_NOT_FOUND)
        return self._serialize_template(updated)

    async def delete_template(self, template_id: int, scope: dict[str, Any]) -> dict[str, bool]:
        validated_scope = await self.validate_scope(scope)
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            deleted = await self.repository.delete_template(
                template_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        if not deleted:
            raise BroadcastError(BROADCAST_TEMPLATE_NOT_FOUND)
        return {'deleted': True}

    async def render_template(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        template_id = payload.get('template_id')
        content = payload.get('content')
        if bool(template_id) == bool(content):
            raise BroadcastError(TEMPLATE_RENDER_INPUT_INVALID)

        if template_id:
            template = await self.repository.get_template(
                int(template_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
            )
            if template is None:
                raise BroadcastError(BROADCAST_TEMPLATE_NOT_FOUND)
            content_text = str(template.content)
        else:
            content_text = str(content or '').strip()
            if not content_text:
                raise BroadcastError(TEMPLATE_RENDER_INPUT_INVALID)

        return safe_render_template(content_text, dict(payload.get('variables') or {}))

    async def get_variable_profile(self, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        profile = await self.repository.get_variable_profile(**validated_scope)
        if profile is None:
            return {
                'group_field': None,
                'mapping_rules': [],
            }
        return self.ap.persistence_mgr.serialize_model(
            persistence_broadcast.BroadcastVariableProfile,
            profile,
        )

    async def save_variable_profile(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        group_field = payload.get('group_field')
        mapping_rules = payload.get('mapping_rules') or []
        self._validate_variable_profile_payload(group_field, mapping_rules)

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await self.repository.upsert_variable_profile(
                conn,
                {
                    **validated_scope,
                    'group_field': group_field,
                    'mapping_rules': mapping_rules,
                },
            )

        return await self.get_variable_profile(validated_scope)

    async def list_group_rules(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        rows = await self.repository.list_group_rules(**validated_scope)
        return [
            self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupRule, row)
            for row in rows
        ]

    async def create_group_rule(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        normalized = self._normalize_group_rule_payload(payload)
        try:
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                rule_id = await self.repository.create_group_rule(
                    conn,
                    {
                        **validated_scope,
                        **normalized,
                    },
                )
        except IntegrityError as exc:
            raise self._map_integrity_error(exc) from exc
        rule = await self.repository.get_group_rule(rule_id, **validated_scope)
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupRule, rule)

    async def update_group_rule(
        self,
        rule_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        normalized = self._normalize_group_rule_payload(payload)
        try:
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                updated = await self.repository.update_group_rule(
                    rule_id,
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates=normalized,
                    conn=conn,
                )
        except IntegrityError as exc:
            raise self._map_integrity_error(exc) from exc
        if updated is None:
            raise BroadcastError(BROADCAST_GROUP_RULE_NOT_FOUND)
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupRule, updated)

    async def delete_group_rule(self, rule_id: int, scope: dict[str, Any]) -> dict[str, bool]:
        validated_scope = await self.validate_scope(scope)
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            deleted = await self.repository.delete_group_rule(
                rule_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        if not deleted:
            raise BroadcastError(BROADCAST_GROUP_RULE_NOT_FOUND)
        return {'deleted': True}

    async def match_group_rule(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        source_value = str(payload.get('source_value') or '').strip()
        if not source_value:
            return {
                'matched': False,
                'rule_id': None,
                'target_conversation_name': None,
                'match_type': None,
            }

        rows = await self.repository.list_group_rules(**validated_scope)
        for row in rows:
            if not bool(row.enabled):
                continue
            if self._rule_matches(row.match_type, row.match_expression, source_value):
                return {
                    'matched': True,
                    'rule_id': int(row.id),
                    'target_conversation_name': row.target_conversation_name,
                    'match_type': row.match_type,
                }
        return {
            'matched': False,
            'rule_id': None,
            'target_conversation_name': None,
            'match_type': None,
        }

    async def list_group_names(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        rows = await self.repository.list_group_names(**validated_scope)
        return [
            self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupName, row)
            for row in rows
        ]

    async def create_group_names(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        raw_names = payload.get('names')
        if raw_names is None:
            raw_names = [payload.get('name')]

        normalized_names: list[str] = []
        seen: set[str] = set()
        for item in raw_names:
            name = str(item or '').strip()
            if not name or name in seen:
                continue
            seen.add(name)
            normalized_names.append(name)

        if not normalized_names:
            return {
                'group_names': await self.list_group_names(validated_scope),
            }

        try:
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                for name in normalized_names:
                    await self.repository.create_group_name(
                        conn,
                        {
                            **validated_scope,
                            'name': name,
                        },
                    )
        except IntegrityError as exc:
            raise self._map_integrity_error(exc) from exc

        return {
            'group_names': await self.list_group_names(validated_scope),
        }

    async def delete_group_name(self, group_name_id: int, scope: dict[str, Any]) -> dict[str, bool]:
        validated_scope = await self.validate_scope(scope)
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            deleted = await self.repository.delete_group_name(
                group_name_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        if not deleted:
            raise BroadcastError(BROADCAST_GROUP_NAME_NOT_FOUND)
        return {'deleted': True}

    @staticmethod
    def extract_template_variables(content: str) -> list[str]:
        return extract_variables(content)

    def _normalize_template_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get('name') or '').strip()
        content = str(payload.get('content') or '').strip()
        if not name:
            raise BroadcastError(BROADCAST_TEMPLATE_NAME_DUPLICATE)
        if not content:
            raise BroadcastError(BROADCAST_TEMPLATE_CONTENT_REQUIRED)
        return {
            'name': name,
            'content': content,
            'variables': self.extract_template_variables(content),
            'enabled': bool(payload.get('enabled', True)),
        }

    def _validate_variable_profile_payload(
        self,
        group_field: Any,
        mapping_rules: list[dict[str, Any]],
    ) -> None:
        issues: list[str] = []
        normalized_group_field = str(group_field or '').strip()
        seen_variable_keys: set[str] = set()
        valid_merge_modes = set(VALID_MERGE_MODES)

        if not normalized_group_field:
            issues.append('请填写分组字段')
        elif '{{' in normalized_group_field or '}}' in normalized_group_field:
            normalized_label = normalized_group_field.replace('{', '').replace('}', '') or '客户名称'
            issues.append(f'请填写“{normalized_label}”，不要填写“{normalized_group_field}”')

        if not mapping_rules:
            issues.append('请至少添加一条变量对应规则')

        for index, item in enumerate(mapping_rules, start=1):
            source_field = str(item.get('source_field') or '').strip()
            variable_key = str(item.get('variable_key') or '').strip()
            merge_mode = str(item.get('merge_mode') or '').strip()
            order = item.get('order')

            if source_field == '' and variable_key == '':
                issues.append(f'第 {index} 条规则为空，请删除或补全后再保存')
                continue

            if not source_field and variable_key:
                issues.append(f'第 {index} 条规则缺少表格字段')
            if source_field and not variable_key:
                issues.append(f'第 {index} 条规则缺少消息变量')

            if '{{' in source_field or '}}' in source_field:
                normalized_label = source_field.replace('{', '').replace('}', '') or '客户名称'
                issues.append(f'请填写“{normalized_label}”，不要填写“{source_field}”')
            if '{{' in variable_key or '}}' in variable_key:
                field_label = source_field or '消息变量'
                issues.append(f'请填写“{field_label}”，不要填写“{variable_key}”')

            if merge_mode not in valid_merge_modes:
                issues.append(f'第 {index} 条规则的多条数据处理方式无效')

            try:
                normalized_order = int(order)
            except (TypeError, ValueError):
                normalized_order = 0
            if normalized_order <= 0:
                issues.append(f'第 {index} 条规则的显示顺序无效')

            if variable_key:
                if variable_key in seen_variable_keys:
                    issues.append(f'消息变量“{variable_key}”重复')
                else:
                    seen_variable_keys.add(variable_key)

        if issues:
            message = (
                '变量配置填写不完整，请检查后重试'
                if any(
                    item in issues
                    for item in (
                        '请填写分组字段',
                        '请至少添加一条变量对应规则',
                    )
                )
                or any('缺少' in item for item in issues)
                else '变量配置填写有误，请按提示修改'
            )
            raise BroadcastError(
                BROADCAST_VARIABLE_PROFILE_INVALID,
                message,
                issues,
            )

    def _normalize_group_rule_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        match_type = str(payload.get('match_type') or '').strip()
        expression = str(payload.get('match_expression') or '').strip()
        source_value = str(payload.get('source_value') or '').strip()
        target_conversation_name = str(payload.get('target_conversation_name') or '').strip()
        if match_type not in VALID_MATCH_TYPES or not source_value or not target_conversation_name:
            raise BroadcastError(BROADCAST_GROUP_RULE_REGEX_INVALID)
        if match_type == 'regex':
            try:
                re.compile(expression)
            except re.error as exc:
                raise BroadcastError(BROADCAST_GROUP_RULE_REGEX_INVALID, str(exc)) from exc
        elif not expression:
            raise BroadcastError(BROADCAST_GROUP_RULE_REGEX_INVALID)

        try:
            priority = int(payload.get('priority') or 0)
        except (TypeError, ValueError) as exc:
            raise BroadcastError(BROADCAST_GROUP_RULE_REGEX_INVALID) from exc

        return {
            'source_value': source_value,
            'match_type': match_type,
            'match_expression': expression,
            'target_conversation_name': target_conversation_name,
            'priority': priority,
            'enabled': bool(payload.get('enabled', True)),
        }

    def _serialize_template(self, row) -> dict[str, Any]:
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastTemplate, row)

    def _rule_matches(self, match_type: str, expression: str, source_value: str) -> bool:
        if match_type == 'exact':
            return source_value == expression
        if match_type == 'contains':
            return expression in source_value
        if match_type == 'regex':
            return re.search(expression, source_value) is not None
        return False

    def _map_integrity_error(self, exc: IntegrityError) -> BroadcastError:
        message = str(exc.orig).lower() if getattr(exc, 'orig', None) is not None else str(exc).lower()
        if 'broadcast_templates' in message:
            return BroadcastError(BROADCAST_TEMPLATE_NAME_DUPLICATE)
        if 'broadcast_group_rules' in message:
            return BroadcastError(BROADCAST_GROUP_RULE_DUPLICATE)
        if 'broadcast_group_names' in message:
            return BroadcastError(BROADCAST_GROUP_NAME_DUPLICATE)
        return BroadcastError(BROADCAST_VARIABLE_PROFILE_INVALID)

    async def _get_bound_connector_id(self, bot_uuid: str) -> str | None:
        result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.ChannelAccount.connector_id)
            .join(
                persistence_database_mode.BotChannelBinding,
                persistence_database_mode.BotChannelBinding.channel_account_id
                == persistence_database_mode.ChannelAccount.id,
            )
            .where(persistence_database_mode.BotChannelBinding.bot_uuid == bot_uuid)
            .limit(1)
        )
        scalar = getattr(result, 'scalar', None)
        value = scalar() if callable(scalar) else None
        return str(value) if value is not None else None


from ..entity.persistence import broadcast as persistence_broadcast  # noqa: E402
from ..entity.persistence import database_mode as persistence_database_mode  # noqa: E402
