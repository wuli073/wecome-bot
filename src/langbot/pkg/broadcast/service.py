from __future__ import annotations

import json
import re
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import sqlalchemy
from sqlalchemy.exc import IntegrityError

from .errors import (
    BROADCAST_DRAFT_BODY_EMPTY,
    BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN,
    BROADCAST_DRAFT_NOT_FOUND,
    BROADCAST_DRAFT_SCOPE_MISMATCH,
    BROADCAST_DRAFT_STALE_CONFIRM_FORBIDDEN,
    BROADCAST_DRAFT_STATUS_INVALID,
    BROADCAST_EXECUTION_BATCH_NOT_FOUND,
    BROADCAST_EXECUTION_BATCH_STATUS_INVALID,
    BROADCAST_EXECUTION_CONFIRMATION_EXPIRED,
    BROADCAST_EXECUTION_CONFIRMATION_INVALID,
    BROADCAST_EXECUTION_CONFIRMATION_REQUIRED,
    BROADCAST_EXECUTION_DRAFT_LIMIT_EXCEEDED,
    BROADCAST_EXECUTION_DRAFT_NOT_READY,
    BROADCAST_EXECUTION_DRAFT_STALE,
    BROADCAST_EXECUTION_MODE_INVALID,
    BROADCAST_EXECUTION_SCOPE_MISMATCH,
    BROADCAST_EXECUTION_RUNTIME_TASK_ID_CONFLICT,
    BROADCAST_EXECUTION_SEND_DISABLED,
    BROADCAST_EXECUTION_SEND_TRIGGERED,
    BROADCAST_EXECUTION_RESULT_PERSISTENCE_FAILED,
    BROADCAST_EXECUTION_TASK_NOT_FOUND,
    BROADCAST_EXECUTION_TASK_STATUS_INVALID,
    BROADCAST_EXECUTION_HEALTH_CHECK_FAILED,
    BROADCAST_IMPORT_FIELDS_MISSING,
    BROADCAST_IMPORT_FILE_INVALID,
    BROADCAST_IMPORT_GROUP_FIELD_REQUIRED,
    BROADCAST_IMPORT_NOT_FOUND,
    BROADCAST_IMPORT_READY_DRAFT_EXISTS,
    BROADCAST_IMPORT_REMATCH_FIELDS_MISSING,
    BROADCAST_IMPORT_VARIABLE_PROFILE_REQUIRED,
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
from .draft_generator import generate_group_draft
from .executors.registry import build_executor
from .file_parser import BroadcastFileParserError, parse_import_file
from .group_matcher import match_group
from .import_processor import (
    BroadcastImportProcessorError,
    calculate_batch_stats,
    classify_import_rows,
    validate_import_headers,
    validate_rematch_headers,
)
from .repository import BroadcastRepository
from .runtime_gateway import BroadcastRuntimeGateway
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
        return [self._serialize_group_rule(row) for row in rows]

    async def create_group_rule(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        normalized = self._normalize_group_rule_payload(payload)
        await self._validate_group_rule_target(validated_scope, normalized['target_conversation_name'])
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
        return self._serialize_group_rule(rule)

    async def update_group_rule(
        self,
        rule_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        normalized = self._normalize_group_rule_payload(payload)
        await self._validate_group_rule_target(validated_scope, normalized['target_conversation_name'])
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
        return self._serialize_group_rule(updated)

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
        for row in self._iter_matchable_group_rules(rows):
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
                            'external_conversation_id': None,
                        },
                    )
        except IntegrityError as exc:
            raise self._map_integrity_error(exc) from exc

        return {
            'group_names': await self.list_group_names(validated_scope),
        }

    async def sync_group_names_from_conversations(self, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        conversations = await self.repository.list_database_conversations_for_group_sync(
            connector_id=validated_scope['connector_id']
        )
        stats = {
            'scanned': 0,
            'inserted': 0,
            'updated': 0,
            'unchanged': 0,
            'skipped': 0,
            'errors': [],
        }

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            for conversation in conversations:
                if str(conversation.conversation_type) != 'group':
                    stats['skipped'] += 1
                    continue

                external_conversation_id = str(conversation.external_conversation_id or '').strip()
                conversation_name = str(conversation.conversation_name or '').strip()
                if not external_conversation_id or not conversation_name:
                    stats['skipped'] += 1
                    continue

                stats['scanned'] += 1
                existing = await self.repository.get_group_name_by_external_conversation_id(
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    external_conversation_id=external_conversation_id,
                    conn=conn,
                )
                if existing is None:
                    await self.repository.create_group_name(
                        conn,
                        {
                            **validated_scope,
                            'name': conversation_name,
                            'external_conversation_id': external_conversation_id,
                        },
                    )
                    stats['inserted'] += 1
                    continue

                if str(existing.name) != conversation_name:
                    await self.repository.update_group_name(
                        int(existing.id),
                        bot_uuid=validated_scope['bot_uuid'],
                        connector_id=validated_scope['connector_id'],
                        updates={'name': conversation_name},
                        conn=conn,
                    )
                    stats['updated'] += 1
                    continue

                stats['unchanged'] += 1

        return stats

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

    async def upload_import(self, scope: dict[str, Any], file_payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        variable_profile = await self.repository.get_variable_profile(**validated_scope)
        if variable_profile is None:
            raise BroadcastError(
                BROADCAST_IMPORT_VARIABLE_PROFILE_REQUIRED,
                '璇峰厛閰嶇疆鍙橀噺瀵瑰簲鍏崇郴鍚庡啀瀵煎叆鏂囦欢',
            )
        if not str(variable_profile.group_field or '').strip():
            raise BroadcastError(
                BROADCAST_IMPORT_GROUP_FIELD_REQUIRED,
                '璇峰厛璁剧疆瀹㈡埛鍒嗙粍瀛楁鍚庡啀瀵煎叆鏂囦欢',
            )

        try:
            parsed = await parse_import_file(file_payload['filename'], file_payload['body'])
            validate_import_headers(
                headers=list(parsed['headers']),
                variable_profile={
                    'group_field': variable_profile.group_field,
                    'mapping_rules': list(variable_profile.mapping_rules or []),
                },
            )
        except BroadcastFileParserError as exc:
            raise BroadcastError(BROADCAST_IMPORT_FILE_INVALID, exc.message) from exc
        except BroadcastImportProcessorError as exc:
            raise self._map_import_processor_error(exc) from exc

        rules = await self.repository.list_group_rules(**validated_scope)
        serialized_rules = [
            self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupRule, row)
            for row in self._iter_matchable_group_rules(rules)
        ]
        group_names = [item.name for item in await self.repository.list_group_names(**validated_scope)]
        classified_rows = classify_import_rows(
            rows=list(parsed['rows']),
            group_field=str(variable_profile.group_field),
            match_resolver=lambda group_value: match_group(
                group_value=group_value,
                rules=serialized_rules,
                group_names=group_names,
            ),
        )
        stats = calculate_batch_stats(classified_rows)

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            import_id = await self.repository.create_import_batch(
                conn,
                {
                    **validated_scope,
                    'original_file_name': str(file_payload['filename']),
                    'file_type': parsed['file_type'],
                    'worksheet_name': parsed['worksheet_name'],
                    'status': 'imported',
                    'drafts_stale': False,
                    **stats,
                },
            )
            await self.repository.replace_import_rows(conn, import_batch_id=import_id, rows=classified_rows)

        return await self.get_import_detail(import_id, validated_scope, {})

    async def list_import_batches(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        rows = await self.repository.list_import_batches(**validated_scope)
        return [self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastImportBatch, row) for row in rows]

    async def get_import_detail(
        self,
        import_id: int,
        scope: dict[str, Any],
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_import_batch(import_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_IMPORT_NOT_FOUND, '褰撳墠瀵煎叆鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')

        page = filters.get('page')
        page_size = filters.get('page_size')
        rows = await self.repository.list_import_rows(
            import_batch_id=import_id,
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
            match_status=filters.get('match_status'),
            keyword=filters.get('keyword'),
            page=page,
            page_size=page_size,
        )
        data = self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastImportBatch, batch)
        data['rows'] = [
            self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastImportRow, row) for row in rows
        ]
        return data

    async def delete_import(self, import_id: int, scope: dict[str, Any]) -> dict[str, bool]:
        validated_scope = await self.validate_scope(scope)
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            deleted = await self.repository.delete_import_batch(import_id, conn=conn, **validated_scope)
        if not deleted:
            raise BroadcastError(BROADCAST_IMPORT_NOT_FOUND, '褰撳墠瀵煎叆鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        return {'deleted': True}

    async def rematch_import(self, import_id: int, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_import_batch(import_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_IMPORT_NOT_FOUND, '褰撳墠瀵煎叆鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        ready_drafts = await self.repository.list_drafts(
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
            import_batch_id=import_id,
            status='ready',
        )
        if ready_drafts:
            raise BroadcastError(
                BROADCAST_IMPORT_READY_DRAFT_EXISTS,
                '当前批次存在已确认草稿，请先撤回确认后再重新匹配。',
            )

        variable_profile = await self.repository.get_variable_profile(**validated_scope)
        if variable_profile is None:
            raise BroadcastError(
                BROADCAST_IMPORT_VARIABLE_PROFILE_REQUIRED,
                '璇峰厛閰嶇疆鍙橀噺瀵瑰簲鍏崇郴鍚庡啀瀵煎叆鏂囦欢',
            )

        existing_rows = await self.repository.list_import_rows(
            import_batch_id=import_id,
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
        )
        headers = list(existing_rows[0].raw_data.keys()) if existing_rows else []
        try:
            validate_rematch_headers(
                headers=headers,
                variable_profile={
                    'group_field': variable_profile.group_field,
                    'mapping_rules': list(variable_profile.mapping_rules or []),
                },
            )
        except BroadcastImportProcessorError as exc:
            raise self._map_import_processor_error(exc) from exc

        rules = await self.repository.list_group_rules(**validated_scope)
        serialized_rules = [
            self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupRule, row)
            for row in self._iter_matchable_group_rules(rules)
        ]
        group_names = [item.name for item in await self.repository.list_group_names(**validated_scope)]
        classified_rows = classify_import_rows(
            rows=[
                {
                    'source_row_number': row.source_row_number,
                    'raw_data': row.raw_data,
                }
                for row in existing_rows
            ],
            group_field=str(variable_profile.group_field),
            match_resolver=lambda group_value: match_group(
                group_value=group_value,
                rules=serialized_rules,
                group_names=group_names,
            ),
        )
        stats = calculate_batch_stats(classified_rows)
        existing_non_ready_drafts = await self.repository.list_drafts(
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
            import_batch_id=import_id,
        )
        drafts_stale = any(draft.status in {'pending_review', 'invalid'} for draft in existing_non_ready_drafts)

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await self.repository.replace_import_rows(conn, import_batch_id=import_id, rows=classified_rows)
            await self.repository.update_import_batch(
                import_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={'status': 'matched', 'drafts_stale': drafts_stale, **stats},
                conn=conn,
            )

        return await self.get_import_detail(import_id, validated_scope, {})

    async def generate_import_drafts(
        self,
        import_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_import_batch(import_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_IMPORT_NOT_FOUND, '褰撳墠瀵煎叆鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')

        ready_drafts = await self.repository.list_drafts(
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
            import_batch_id=import_id,
            status='ready',
        )
        if ready_drafts:
            raise BroadcastError(
                BROADCAST_IMPORT_READY_DRAFT_EXISTS,
                '当前批次存在已确认草稿，请先撤回确认后再重新生成。',
            )

        template = await self.repository.get_template(
            int(payload.get('template_id') or 0),
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
        )
        if template is None:
            raise BroadcastError(BROADCAST_TEMPLATE_NOT_FOUND, '褰撳墠妯℃澘涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')

        variable_profile = await self.repository.get_variable_profile(**validated_scope)
        rows = await self.repository.list_import_rows(
            import_batch_id=import_id,
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
        )
        grouped_rows: dict[str, list[Any]] = {}
        for row in rows:
            key = row.group_value or f'__invalid__:{row.source_row_number}'
            grouped_rows.setdefault(key, []).append(row)

        drafts = []
        pending_review_count = 0
        invalid_count = 0
        unmatched_group_count = 0
        for group_key, group_rows in grouped_rows.items():
            first_row = group_rows[0]
            draft = generate_group_draft(
                group_value=first_row.group_value or group_key,
                rows=[{'raw_data': row.raw_data} for row in group_rows],
                mapping_rules=list(variable_profile.mapping_rules or []),
                matched_conversation_name=first_row.matched_conversation_name,
                template_name=str(template.name),
                template_content=str(template.content),
                render_template=safe_render_template,
            )
            if draft['status'] == 'pending_review':
                pending_review_count += 1
            else:
                invalid_count += 1
                if draft['error_message'] == '鏈尮閰嶅埌缇よ亰':
                    unmatched_group_count += 1
            drafts.append(
                {
                    **validated_scope,
                    'import_batch_id': import_id,
                    'group_value': draft['group_value'],
                    'target_conversation_name': draft['target_conversation_name'],
                    'template_id': int(template.id),
                    'template_name_snapshot': draft['template_name_snapshot'],
                    'template_content_snapshot': draft['template_content_snapshot'],
                    'render_variables': draft['render_variables'],
                    'draft_text': draft['draft_text'],
                    'status': draft['status'],
                    'error_message': draft['error_message'],
                }
            )

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await self.repository.replace_drafts(
                conn,
                import_batch_id=import_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                drafts=drafts,
            )
            await self.repository.update_import_batch(
                import_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={'status': 'drafts_generated', 'drafts_stale': False},
                conn=conn,
            )

        return {
            'total_group_count': len(grouped_rows),
            'pending_review_count': pending_review_count,
            'invalid_count': invalid_count,
            'unmatched_group_count': unmatched_group_count,
        }

    async def list_drafts(self, scope: dict[str, Any], filters: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        rows = await self.repository.list_drafts(
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
            import_batch_id=filters.get('import_batch_id'),
            status=filters.get('status'),
            keyword=filters.get('keyword'),
        )
        return [await self._serialize_draft(row) for row in rows]

    async def get_draft_detail(self, draft_id: int, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        draft = await self.repository.get_draft(draft_id, **validated_scope)
        if draft is None:
            raise BroadcastError(BROADCAST_DRAFT_NOT_FOUND, '褰撳墠鑽夌涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        return await self._serialize_draft(draft)

    async def update_draft_text(
        self,
        draft_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        draft = await self.repository.get_draft(draft_id, **validated_scope)
        if draft is None:
            raise BroadcastError(BROADCAST_DRAFT_NOT_FOUND, '褰撳墠鑽夌涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')

        draft_text = str(payload.get('draft_text') or '')
        if not draft_text.strip():
            raise BroadcastError(BROADCAST_DRAFT_BODY_EMPTY, '鑽夌姝ｆ枃涓嶈兘涓虹┖')

        updates = {'draft_text': draft_text}
        message = None
        if draft.status == 'ready':
            updates['status'] = 'pending_review'
            message = '草稿内容已修改，请重新确认'
        elif draft.status == 'pending_review':
            updates['status'] = 'pending_review'
        elif draft.status == 'invalid':
            updates['status'] = 'invalid'

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated = await self.repository.update_draft(
                draft_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates=updates,
                conn=conn,
            )
        if updated is None:
            raise BroadcastError(BROADCAST_DRAFT_NOT_FOUND, '褰撳墠鑽夌涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        result = await self._serialize_draft(updated)
        result['message'] = message
        return result

    async def update_draft_statuses(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        draft_ids = [int(draft_id) for draft_id in payload.get('draft_ids') or []]
        target_status = str(payload.get('status') or '').strip()
        if target_status not in {'ready', 'pending_review'}:
            raise BroadcastError(BROADCAST_DRAFT_STATUS_INVALID, '鑽夌鐘舵€佹棤鏁堬紝璇峰埛鏂板悗閲嶈瘯')

        drafts = [
            await self.repository.get_draft(draft_id, **validated_scope)
            for draft_id in draft_ids
        ]
        if not draft_ids or any(draft is None for draft in drafts):
            raise BroadcastError(
                BROADCAST_DRAFT_SCOPE_MISMATCH,
                '鎵€閫夎崏绋夸腑鍖呭惈鏃犳潈鎿嶄綔鐨勬暟鎹紝璇峰埛鏂板悗閲嶈瘯',
            )

        for draft in drafts:
            batch = await self.repository.get_import_batch(
                int(draft.import_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
            )
            if batch is None:
                raise BroadcastError(BROADCAST_IMPORT_NOT_FOUND, '褰撳墠瀵煎叆鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
            if target_status == 'ready':
                if draft.status == 'invalid':
                    raise BroadcastError(
                        BROADCAST_DRAFT_INVALID_CONFIRM_FORBIDDEN,
                        '褰撳墠鑽夌鐢熸垚澶辫触锛屼笉鑳界洿鎺ョ‘璁わ紝璇蜂慨澶嶉厤缃悗閲嶆柊鐢熸垚',
                    )
                if batch.drafts_stale:
                    raise BroadcastError(
                        BROADCAST_DRAFT_STALE_CONFIRM_FORBIDDEN,
                        '当前草稿已过期，请重新生成草稿后再确认。',
                    )

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated_count = await self.repository.update_draft_statuses(
                draft_ids=draft_ids,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                status=target_status,
                conn=conn,
            )
        return {'updated_count': updated_count}

    async def create_execution_batch(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        mode = str(payload.get('mode') or '').strip()
        if mode not in {'paste_only', 'send'}:
            raise BroadcastError(BROADCAST_EXECUTION_MODE_INVALID, '执行模式无效')

        raw_draft_ids = payload.get('draft_ids')
        if raw_draft_ids is None and payload.get('draft_id') is not None:
            raw_draft_ids = [payload.get('draft_id')]
        draft_ids = [int(draft_id) for draft_id in list(raw_draft_ids or [])]
        draft_ids = list(dict.fromkeys(draft_ids))
        if not draft_ids:
            raise BroadcastError(BROADCAST_EXECUTION_DRAFT_LIMIT_EXCEEDED, '至少需要选择一条草稿')
        if mode == 'send' and len(draft_ids) != 1:
            raise BroadcastError(BROADCAST_EXECUTION_DRAFT_LIMIT_EXCEEDED, '真实发送当前仅允许单条任务')

        operator = str(payload.get('operator') or '').strip() or 'unknown'
        if mode == 'send':
            self._assert_send_feature_enabled(validated_scope)

        drafts = []
        for draft_id in draft_ids:
            draft = await self.repository.get_draft(draft_id, **validated_scope)
            if draft is None:
                raise BroadcastError(
                    BROADCAST_EXECUTION_SCOPE_MISMATCH,
                    '所选草稿不属于当前 bot / connector 作用域',
                )
            await self._assert_draft_ready_for_execution(draft, validated_scope)
            drafts.append(draft)

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            batch_id = await self.repository.create_execution_batch(
                conn,
                {
                    'bot_uuid': validated_scope['bot_uuid'],
                    'connector_id': validated_scope['connector_id'],
                    'channel': 'wxwork_database',
                    'mode': mode,
                    'status': 'created',
                    'total_tasks': len(drafts),
                    'pending_tasks': len(drafts),
                    'running_tasks': 0,
                    'succeeded_tasks': 0,
                    'failed_tasks': 0,
                    'cancelled_tasks': 0,
                    'interrupted_tasks': 0,
                    'created_by': operator,
                    'last_action_by': operator,
                    'error_message': None,
                    'version': 1,
                },
            )
            for index, draft in enumerate(drafts, start=1):
                action = 'send_message' if mode == 'send' else 'paste_draft'
                request_digest = self._build_execution_request_digest(
                    action=action,
                    channel='wxwork_database',
                    target_conversation=str(draft.target_conversation_name or ''),
                    draft_text=str(draft.draft_text or ''),
                )
                task_id = await self.repository.create_execution_task(
                    conn,
                    {
                        'execution_batch_id': batch_id,
                        'draft_id': int(draft.id),
                        'draft_text_snapshot': str(draft.draft_text),
                        'target_conversation_snapshot': str(draft.target_conversation_name),
                        'channel': 'wxwork_database',
                        'action': action,
                        'status': 'pending',
                        'sequence_no': index,
                        'attempt_count': 0,
                        'max_attempts': 1,
                        'idempotency_key': f'broadcast:{batch_id + 1000000}:{index}',
                        'request_digest': request_digest,
                        'runtime_task_id': None,
                        'error_code': None,
                        'error_message': None,
                        'operator_note': None,
                    },
                )
                await self.repository.update_execution_task(
                    task_id,
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={'idempotency_key': f'broadcast:{task_id}:1'},
                    conn=conn,
                )
        return await self.get_execution_batch_detail(batch_id, validated_scope)

    async def list_execution_batches(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        rows = await self.repository.list_execution_batches(**validated_scope)
        return [self._serialize_execution_batch(row) for row in rows]

    async def get_execution_batch_detail(self, batch_id: int, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_execution_batch(batch_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_NOT_FOUND, '鎵ц鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        tasks = await self.repository.list_execution_tasks(batch_id, **validated_scope)
        data = self._serialize_execution_batch(batch)
        data['tasks'] = [self._serialize_execution_task(row) for row in tasks]
        return data

    async def get_execution_task_detail(self, task_id: int, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '鎵ц浠诲姟涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        return self._serialize_execution_task(task)
    async def start_execution_batch(
        self,
        batch_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._transition_execution_batch_to_queued(batch_id, scope, payload, allowed_statuses={'created', 'paused', 'interrupted'})

    async def pause_execution_batch(
        self,
        batch_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_execution_batch(batch_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_NOT_FOUND, '执行批次不存在或已被删除')
        if str(batch.status) not in {'queued', 'running'}:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_STATUS_INVALID, '当前批次状态不允许暂停')

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated = await self.repository.update_execution_batch(
                batch_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'paused',
                    'paused_at': sqlalchemy.func.now(),
                    'last_action_by': str(payload.get('operator') or '').strip() or 'unknown',
                },
                conn=conn,
            )
        return self._serialize_execution_batch(updated)

    async def resume_execution_batch(
        self,
        batch_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._transition_execution_batch_to_queued(batch_id, scope, payload, allowed_statuses={'paused'})

    async def cancel_execution_batch(
        self,
        batch_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_execution_batch(batch_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_NOT_FOUND, '执行批次不存在或已被删除')
        if str(batch.status) not in {'created', 'queued', 'running', 'paused', 'interrupted', 'partially_failed', 'failed'}:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_STATUS_INVALID, '当前批次状态不允许取消')

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            tasks = await self.repository.list_execution_tasks(batch_id, **validated_scope, conn=conn)
            for task in tasks:
                if str(task.status) != 'pending':
                    continue
                await self.repository.update_execution_task(
                    int(task.id),
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': 'cancelled',
                        'cancelled_at': sqlalchemy.func.now(),
                        'finished_at': sqlalchemy.func.now(),
                    },
                    conn=conn,
                )
            updated = await self.repository.update_execution_batch(
                batch_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'cancelled',
                    'cancelled_at': sqlalchemy.func.now(),
                    'last_action_by': str(payload.get('operator') or '').strip() or 'unknown',
                },
                conn=conn,
            )
            updated = await self.repository.recompute_execution_batch_counts(
                batch_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        return self._serialize_execution_batch(updated)

    async def run_next_execution_task(self) -> bool:
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            claimed = await self.repository.claim_next_execution_task(conn)
        if claimed is None:
            return False
        await self._execute_execution_task(
            int(claimed['task'].id),
            claimed['scope'],
            {'operator': 'broadcast-worker'},
            claimed=True,
        )
        return True

    async def start_execution_task(
        self,
        task_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._execute_execution_task(task_id, scope, payload, claimed=False)

    async def _execute_execution_task(
        self,
        task_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
        *,
        claimed: bool,
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行任务不存在或已被删除')
        if str(task.action) != 'paste_draft':
            raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务不支持通过 paste 执行')
        if claimed:
            if task.status != 'running':
                raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务尚未被 worker 领取')
        else:
            if task.status != 'pending':
                raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务状态不允许执行')
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                await self.repository.update_execution_task(
                    task_id,
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': 'running',
                        'started_at': sqlalchemy.func.now(),
                    },
                    conn=conn,
                )
                await self.repository.update_execution_batch(
                    int(task.execution_batch_id),
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': 'running',
                        'started_at': sqlalchemy.func.now(),
                        'paused_at': None,
                    },
                    conn=conn,
                )
                task = await self.repository.get_execution_task(task_id, **validated_scope, conn=conn)

        gateway = self._get_runtime_gateway()
        gateway.assert_force_disable_send()
        executor = build_executor(str(task.channel), gateway)
        executor.validate_capability(str(task.action))
        attempt_no = int(task.attempt_count or 0) + 1
        idempotency_key = f'broadcast:{task_id}:{attempt_no}'

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated = await self.repository.update_execution_task(
                task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'attempt_count': attempt_no,
                    'idempotency_key': idempotency_key,
                    'error_code': None,
                    'error_message': None,
                    'runtime_task_id': None,
                    'started_at': sqlalchemy.func.now(),
                },
                conn=conn,
            )
            attempt_id = await self.repository.create_execution_attempt(
                conn,
                {
                    'execution_task_id': task_id,
                    'attempt_no': attempt_no,
                    'idempotency_key': idempotency_key,
                    'request_digest': str(task.request_digest),
                    'runtime_task_id': None,
                    'request_summary': json.dumps(
                        {
                            'action': str(task.action),
                            'channel': str(task.channel),
                            'target_conversation': str(task.target_conversation_snapshot),
                        },
                        ensure_ascii=False,
                    ),
                    'response_summary': None,
                    'status': 'running',
                    'error_code': None,
                    'error_message': None,
                    'finished_at': None,
                },
            )
            await self.repository.recompute_execution_batch_counts(
                int(task.execution_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )

        runtime_result = None
        task_status = 'interrupted'
        error_code = None
        error_message = None
        try:
            runtime_result = await executor.paste_draft(
                conversation_name=str(task.target_conversation_snapshot),
                draft_text=str(task.draft_text_snapshot),
                idempotency_key=idempotency_key,
                request_digest=str(task.request_digest),
            )
            evidence = executor.normalize_evidence(runtime_result)
            if bool(evidence.get('send_triggered', False)):
                task_status = 'failed'
                error_code = BROADCAST_EXECUTION_SEND_TRIGGERED
                error_message = '检测到发送动作，已按安全失败处理'
            elif not bool(evidence.get('content_verified', False)):
                task_status = 'interrupted'
                error_code = (
                    str(runtime_result.get('errorCode') or runtime_result.get('error_code') or '').strip()
                    or 'PASTE_VERIFICATION_FAILED'
                )
                error_message = (
                    'Paste completed but input content could not be verified'
                    if error_code == 'PASTE_VERIFICATION_UNAVAILABLE'
                    else 'Paste completed but input content does not match expected text'
                )
            else:
                runtime_status = str(runtime_result.get('status') or '')
                task_status = self._coerce_terminal_task_status(runtime_status)
                error_code = (
                    str(runtime_result.get('errorCode') or runtime_result.get('error_code') or '').strip() or None
                )
                error_message = (
                    str(runtime_result.get('errorMessage') or runtime_result.get('error_message') or '').strip()
                    or None
                )
        except BroadcastError as exc:
            task_status = 'failed'
            error_code = exc.code
            error_message = exc.message
        except Exception as exc:
            task_status = 'interrupted'
            error_code = exc.__class__.__name__
            error_message = str(exc)

        runtime_task_id = str(runtime_result.get('id') or '').strip() or None if runtime_result else None
        if runtime_task_id:
            existing_attempt = await self.repository.get_execution_attempt_by_runtime_task_id(
                runtime_task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
            )
            if existing_attempt is not None and int(existing_attempt.execution_task_id) != int(task_id):
                task_status = 'failed'
                error_code = BROADCAST_EXECUTION_RUNTIME_TASK_ID_CONFLICT
                error_message = 'Runtime task ID 与其他执行任务冲突'
        persisted_runtime_task_id = (
            None if error_code == BROADCAST_EXECUTION_RUNTIME_TASK_ID_CONFLICT else runtime_task_id
        )

        sanitized_runtime_result = self._sanitize_runtime_result(runtime_result)
        sanitized_evidence = None
        if runtime_result is not None:
            evidence = executor.normalize_evidence(runtime_result)
            sanitized_evidence = {
                **evidence,
                'technical_details': self._sanitize_technical_details(evidence.get('technical_details')),
            }

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            try:
                await self.repository.update_execution_attempt(
                    int(attempt_id),
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': task_status,
                        'runtime_task_id': persisted_runtime_task_id,
                        'response_summary': json.dumps(sanitized_runtime_result, ensure_ascii=False)
                        if sanitized_runtime_result is not None
                        else None,
                        'error_code': error_code,
                        'error_message': error_message,
                        'finished_at': sqlalchemy.func.now(),
                    },
                    conn=conn,
                )
                if sanitized_evidence is not None:
                    await self.repository.create_execution_evidence(
                        conn,
                        {
                            'execution_attempt_id': int(attempt_id),
                            'window_title': sanitized_evidence.get('window_title'),
                            'target_conversation': sanitized_evidence.get('target_conversation'),
                            'action': sanitized_evidence.get('action') or str(task.action),
                            'input_located': bool(sanitized_evidence.get('input_located', False)),
                            'draft_written': bool(sanitized_evidence.get('draft_written', False)),
                            'send_triggered': bool(sanitized_evidence.get('send_triggered', False)),
                            'clipboard_restored': bool(sanitized_evidence.get('clipboard_restored', False)),
                            'runtime_state': sanitized_evidence.get('runtime_state'),
                            'evidence_summary': sanitized_evidence.get('evidence_summary'),
                            'technical_details': json.dumps(
                                sanitized_evidence.get('technical_details'),
                                ensure_ascii=False,
                            )
                            if sanitized_evidence.get('technical_details') is not None
                            else None,
                        },
                    )
                updated = await self.repository.update_execution_task(
                    task_id,
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': task_status,
                        'runtime_task_id': persisted_runtime_task_id,
                        'error_code': error_code,
                        'error_message': error_message,
                        'finished_at': sqlalchemy.func.now(),
                    },
                    conn=conn,
                )
                await self.repository.recompute_execution_batch_counts(
                    int(task.execution_batch_id),
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    conn=conn,
                )
            except Exception:
                updated = await self.repository.update_execution_task(
                    task_id,
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': 'interrupted',
                        'runtime_task_id': persisted_runtime_task_id,
                        'error_code': BROADCAST_EXECUTION_RESULT_PERSISTENCE_FAILED,
                        'error_message': 'Runtime 已返回，但结果落库失败',
                        'finished_at': sqlalchemy.func.now(),
                    },
                    conn=conn,
                )
                await self.repository.update_execution_attempt(
                    int(attempt_id),
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    updates={
                        'status': 'interrupted',
                        'runtime_task_id': persisted_runtime_task_id,
                        'response_summary': json.dumps(sanitized_runtime_result, ensure_ascii=False)
                        if sanitized_runtime_result is not None
                        else None,
                        'error_code': BROADCAST_EXECUTION_RESULT_PERSISTENCE_FAILED,
                        'error_message': 'Runtime 已返回，但结果落库失败',
                        'finished_at': sqlalchemy.func.now(),
                    },
                    conn=conn,
                )
                await self.repository.recompute_execution_batch_counts(
                    int(task.execution_batch_id),
                    bot_uuid=validated_scope['bot_uuid'],
                    connector_id=validated_scope['connector_id'],
                    conn=conn,
                )
        return self._serialize_execution_task(updated)
    async def cancel_execution_task(
        self,
        task_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行任务不存在或已被删除')
        if task.status != 'pending':
            raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务状态不允许取消')

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated = await self.repository.update_execution_task(
                task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'cancelled',
                    'cancelled_at': sqlalchemy.func.now(),
                    'finished_at': sqlalchemy.func.now(),
                },
                conn=conn,
            )
            await self.repository.recompute_execution_batch_counts(
                int(task.execution_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        return self._serialize_execution_task(updated)

    async def retry_execution_task(
        self,
        task_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行任务不存在或已被删除')
        if task.status not in {'failed', 'interrupted'}:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务状态不允许重试')

        next_attempt_no = int(task.attempt_count or 0) + 1
        operator = str(payload.get('operator') or '').strip() or 'unknown'
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated = await self.repository.update_execution_task(
                task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'pending',
                    'runtime_task_id': None,
                    'error_code': None,
                    'error_message': None,
                    'started_at': None,
                    'finished_at': None,
                    'cancelled_at': None,
                    'idempotency_key': f'broadcast:{task_id}:{next_attempt_no}',
                },
                conn=conn,
            )
            await self.repository.update_execution_batch(
                int(task.execution_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'queued',
                    'paused_at': None,
                    'last_action_by': operator,
                },
                conn=conn,
            )
            await self.repository.recompute_execution_batch_counts(
                int(task.execution_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        self._wake_worker()
        return self._serialize_execution_task(updated)

    async def list_execution_attempts(self, task_id: int, scope: dict[str, Any]) -> list[dict[str, Any]]:
        validated_scope = await self.validate_scope(scope)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行任务不存在或已被删除')
        attempts = await self.repository.list_execution_attempts(task_id, **validated_scope)
        return [self._serialize_execution_attempt(row) for row in attempts]

    async def reconcile_running_executions(self) -> int:
        running_scopes_result = await self.ap.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionTask,
                persistence_broadcast.BroadcastExecutionTask.execution_batch_id
                == persistence_broadcast.BroadcastExecutionBatch.id,
            )
            .where(persistence_broadcast.BroadcastExecutionTask.status == 'running')
            .distinct()
        )
        running_scopes = list(running_scopes_result.all())
        updated_count = 0

        for scope_row in running_scopes:
            bot_uuid = str(scope_row[0])
            connector_id = str(scope_row[1])
            async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
                tasks = await self.repository.list_execution_tasks_by_status(
                    bot_uuid=bot_uuid,
                    connector_id=connector_id,
                    status='running',
                    conn=conn,
                )
                touched_batch_ids: set[int] = set()
                for task in tasks:
                    attempts = await self.repository.list_execution_attempts(
                        int(task.id),
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                        conn=conn,
                    )
                    if attempts:
                        latest_attempt = attempts[-1]
                        if str(latest_attempt.status) == 'running':
                            await self.repository.update_execution_attempt(
                                int(latest_attempt.id),
                                bot_uuid=bot_uuid,
                                connector_id=connector_id,
                                updates={
                                    'status': 'interrupted',
                                    'error_code': 'RECOVERED_ON_STARTUP',
                                    'error_message': '应用重启后中断，需人工重试',
                                    'finished_at': sqlalchemy.func.now(),
                                },
                                conn=conn,
                            )
                    await self.repository.update_execution_task(
                        int(task.id),
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                        updates={
                            'status': 'interrupted',
                            'error_code': 'RECOVERED_ON_STARTUP',
                            'error_message': '应用重启后中断，需人工重试',
                            'finished_at': sqlalchemy.func.now(),
                        },
                        conn=conn,
                    )
                    touched_batch_ids.add(int(task.execution_batch_id))
                    updated_count += 1
                for batch_id in touched_batch_ids:
                    await self.repository.recompute_execution_batch_counts(
                        batch_id,
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                        conn=conn,
                    )

        return updated_count

    async def get_execution_attempt_detail(self, attempt_id: int, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        attempt = await self.repository.get_execution_attempt(attempt_id, **validated_scope)
        if attempt is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行尝试不存在或已被删除')
        return self._serialize_execution_attempt(attempt)

    async def get_execution_evidence(self, attempt_id: int, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        attempt = await self.repository.get_execution_attempt(attempt_id, **validated_scope)
        if attempt is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行尝试不存在或已被删除')
        evidence = await self.repository.get_execution_evidence(attempt_id, **validated_scope)
        if evidence is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行证据不存在或已被删除')
        return self._serialize_execution_evidence(evidence)

    async def get_executor_capabilities(self, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        gateway = self._get_runtime_gateway()
        executor = build_executor('wxwork_database', gateway)
        capability = executor.validate_capability('paste_draft')
        return {
            'channel': 'wxwork_database',
            **capability,
            'supports_send': bool(capability.get('supports_send', False)) and self._is_send_enabled(validated_scope),
        }

    async def get_executor_health(self, scope: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        gateway = self._get_runtime_gateway()
        executor = build_executor('wxwork_database', gateway)
        capability = executor.validate_capability('paste_draft')
        capability_payload = {
            **capability,
            'supports_send': bool(capability.get('supports_send', False)) and self._is_send_enabled(validated_scope),
        }
        try:
            health = await gateway.health_check()
            runtime_status = await gateway.get_capabilities()
            return {
                'channel': 'wxwork_database',
                'available': True,
                'status': str(health.get('status') or 'unknown'),
                'protocol_version': health.get('protocolVersion'),
                'runtime_version': health.get('runtimeVersion'),
                'capability': capability_payload,
                'runtime_status': self._sanitize_runtime_result(runtime_status),
                'error_message': None,
            }
        except Exception as exc:
            return {
                'channel': 'wxwork_database',
                'available': False,
                'status': 'unavailable',
                'protocol_version': None,
                'runtime_version': None,
                'capability': capability_payload,
                'runtime_status': None,
                'error_message': str(exc) or BROADCAST_EXECUTION_HEALTH_CHECK_FAILED,
            }

    async def issue_send_confirmation(self, scope: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        self._assert_send_feature_enabled(validated_scope)
        task_id = int(payload.get('execution_task_id') or 0)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行任务不存在或已被删除')
        batch = await self.repository.get_execution_batch(int(task.execution_batch_id), **validated_scope)
        if batch is None or str(batch.mode) != 'send':
            raise BroadcastError(BROADCAST_EXECUTION_MODE_INVALID, '仅 send 模式任务可申请发送确认')
        if task.status != 'pending':
            raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务状态不允许申请发送确认')

        operator = str(payload.get('operator') or '').strip() or 'unknown'
        token = secrets.token_urlsafe(24)
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            confirmation_id = await self.repository.create_send_confirmation(
                conn,
                {
                    'execution_task_id': task_id,
                    'confirmation_token_hash': token_hash,
                    'issued_at': datetime.now(timezone.utc),
                    'expires_at': expires_at,
                    'used_at': None,
                    'issued_by': operator,
                    'used_by': None,
                    'status': 'issued',
                },
            )
            confirmation = await self.repository.get_send_confirmation(
                confirmation_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        return {
            'id': int(confirmation.id),
            'token': token,
            'expires_at': confirmation.expires_at.isoformat() if confirmation.expires_at else None,
            'execution_task_id': int(task.id),
        }

    async def send_execution_task(
        self,
        task_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        self._assert_send_feature_enabled(validated_scope)
        task = await self.repository.get_execution_task(task_id, **validated_scope)
        if task is None:
            raise BroadcastError(BROADCAST_EXECUTION_TASK_NOT_FOUND, '执行任务不存在或已被删除')
        if str(task.action) != 'send_message':
            raise BroadcastError(BROADCAST_EXECUTION_MODE_INVALID, '当前任务不是发送任务')
        if task.status != 'pending':
            raise BroadcastError(BROADCAST_EXECUTION_TASK_STATUS_INVALID, '当前任务状态不允许发送')

        confirmation_token = str(payload.get('confirmation_token') or '').strip()
        if not confirmation_token:
            raise BroadcastError(BROADCAST_EXECUTION_CONFIRMATION_REQUIRED, '缺少发送确认 token')
        confirmation_hash = hashlib.sha256(confirmation_token.encode('utf-8')).hexdigest()
        confirmation = await self.repository.get_send_confirmation_by_hash(
            confirmation_hash,
            bot_uuid=validated_scope['bot_uuid'],
            connector_id=validated_scope['connector_id'],
        )
        if confirmation is None or int(confirmation.execution_task_id) != int(task.id):
            raise BroadcastError(BROADCAST_EXECUTION_CONFIRMATION_INVALID, '发送确认 token 无效')
        if confirmation.used_at is not None or str(confirmation.status) == 'used':
            raise BroadcastError(BROADCAST_EXECUTION_CONFIRMATION_INVALID, '发送确认 token 已使用')
        expires_at = confirmation.expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                raise BroadcastError(BROADCAST_EXECUTION_CONFIRMATION_EXPIRED, '发送确认 token 已过期')

        gateway = self._get_runtime_gateway()
        executor = build_executor(str(task.channel), gateway)
        capability = executor.validate_capability('paste_draft')
        if not self._is_send_enabled(validated_scope) or not bool(capability.get('supports_send', False)):
            raise BroadcastError(BROADCAST_EXECUTION_SEND_DISABLED, '真实发送功能未开启')

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await self.repository.update_execution_task(
                task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'running',
                    'started_at': sqlalchemy.func.now(),
                    'error_code': None,
                    'error_message': None,
                },
                conn=conn,
            )
            await self.repository.update_execution_batch(
                int(task.execution_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={'status': 'running', 'started_at': sqlalchemy.func.now()},
                conn=conn,
            )

        attempt_no = int(task.attempt_count or 0) + 1
        idempotency_key = f'broadcast:{task_id}:{attempt_no}'
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await self.repository.update_execution_task(
                task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'attempt_count': attempt_no,
                    'idempotency_key': idempotency_key,
                },
                conn=conn,
            )
            attempt_id = await self.repository.create_execution_attempt(
                conn,
                {
                    'execution_task_id': task_id,
                    'attempt_no': attempt_no,
                    'idempotency_key': idempotency_key,
                    'request_digest': str(task.request_digest),
                    'runtime_task_id': None,
                    'request_summary': json.dumps(
                        {
                            'action': 'send_message',
                            'channel': str(task.channel),
                            'target_conversation': str(task.target_conversation_snapshot),
                        },
                        ensure_ascii=False,
                    ),
                    'response_summary': None,
                    'status': 'running',
                    'error_code': None,
                    'error_message': None,
                    'finished_at': None,
                },
            )

        runtime_result = None
        task_status = 'interrupted'
        error_code = None
        error_message = None
        try:
            runtime_result = await executor.send_message(
                conversation_name=str(task.target_conversation_snapshot),
                message_text=str(task.draft_text_snapshot),
                idempotency_key=idempotency_key,
                request_digest=str(task.request_digest),
                confirmation_token=confirmation_token,
            )
            runtime_status = str(runtime_result.get('status') or '')
            task_status = self._coerce_terminal_task_status(runtime_status)
            error_code = str(runtime_result.get('errorCode') or runtime_result.get('error_code') or '').strip() or None
            error_message = str(runtime_result.get('errorMessage') or runtime_result.get('error_message') or '').strip() or None
        except BroadcastError as exc:
            task_status = 'failed'
            error_code = exc.code
            error_message = exc.message
        except Exception as exc:
            task_status = 'interrupted'
            error_code = exc.__class__.__name__
            error_message = str(exc)

        runtime_task_id = str(runtime_result.get('id') or '').strip() or None if runtime_result else None
        sanitized_runtime_result = self._sanitize_runtime_result(runtime_result)
        evidence_payload = None
        if runtime_result is not None:
            evidence = executor.normalize_evidence(runtime_result)
            evidence_payload = {
                'execution_attempt_id': int(attempt_id),
                'window_title': evidence.get('window_title'),
                'target_conversation': evidence.get('target_conversation'),
                'action': evidence.get('action') or 'send_message',
                'input_located': bool(evidence.get('input_located', False)),
                'draft_written': bool(evidence.get('draft_written', False)),
                'send_triggered': bool(evidence.get('send_triggered', False)),
                'clipboard_restored': bool(evidence.get('clipboard_restored', False)),
                'runtime_state': evidence.get('runtime_state'),
                'evidence_summary': evidence.get('evidence_summary'),
                'technical_details': json.dumps(
                    self._sanitize_technical_details(evidence.get('technical_details')),
                    ensure_ascii=False,
                )
                if evidence.get('technical_details') is not None
                else None,
            }

        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            await self.repository.update_execution_attempt(
                int(attempt_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': task_status,
                    'runtime_task_id': runtime_task_id,
                    'response_summary': json.dumps(sanitized_runtime_result, ensure_ascii=False)
                    if sanitized_runtime_result is not None
                    else None,
                    'error_code': error_code,
                    'error_message': error_message,
                    'finished_at': sqlalchemy.func.now(),
                },
                conn=conn,
            )
            if evidence_payload is not None:
                await self.repository.create_execution_evidence(conn, evidence_payload)
            updated = await self.repository.update_execution_task(
                task_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': task_status,
                    'runtime_task_id': runtime_task_id,
                    'error_code': error_code,
                    'error_message': error_message,
                    'finished_at': sqlalchemy.func.now(),
                },
                conn=conn,
            )
            await self.repository.update_send_confirmation(
                int(confirmation.id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'used',
                    'used_at': sqlalchemy.func.now(),
                    'used_by': str(payload.get('operator') or '').strip() or 'unknown',
                },
                conn=conn,
            )
            await self.repository.recompute_execution_batch_counts(
                int(task.execution_batch_id),
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        return self._serialize_execution_task(updated)

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
            normalized_label = normalized_group_field.replace('{', '').replace('}', '') or '瀹㈡埛鍚嶇О'
            issues.append(f'请填写“{normalized_label}”，不要填写“{normalized_group_field}”')

        if not mapping_rules:
            issues.append('请至少添加一条变量对应规则')

        for index, item in enumerate(mapping_rules, start=1):
            source_field = str(item.get('source_field') or '').strip()
            variable_key = str(item.get('variable_key') or '').strip()
            merge_mode = str(item.get('merge_mode') or '').strip()
            order = item.get('order')

            if source_field == '' and variable_key == '':
                issues.append(f'绗?{index} 鏉¤鍒欎负绌猴紝璇峰垹闄ゆ垨琛ュ叏鍚庡啀淇濆瓨')
                continue

            if not source_field and variable_key:
                issues.append(f'第 {index} 条规则缺少表格字段')
            if source_field and not variable_key:
                issues.append(f'第 {index} 条规则缺少消息变量')

            if '{{' in source_field or '}}' in source_field:
                normalized_label = source_field.replace('{', '').replace('}', '') or '瀹㈡埛鍚嶇О'
                issues.append(f'请填写“{normalized_label}”，不要填写“{source_field}”')
            if '{{' in variable_key or '}}' in variable_key:
                field_label = source_field or '娑堟伅鍙橀噺'
                issues.append(f'请填写“{field_label}”，不要填写“{variable_key}”')

            if merge_mode not in valid_merge_modes:
                issues.append(f'绗?{index} 鏉¤鍒欑殑澶氭潯鏁版嵁澶勭悊鏂瑰紡鏃犳晥')

            try:
                normalized_order = int(order)
            except (TypeError, ValueError):
                normalized_order = 0
            if normalized_order <= 0:
                issues.append(f'绗?{index} 鏉¤鍒欑殑鏄剧ず椤哄簭鏃犳晥')

            if variable_key:
                if variable_key in seen_variable_keys:
                    issues.append(f'消息变量“{variable_key}”重复')
                else:
                    seen_variable_keys.add(variable_key)

        if issues:
            message = (
                '鍙橀噺閰嶇疆濉啓涓嶅畬鏁达紝璇锋鏌ュ悗閲嶈瘯'
                if any(
                    item in issues
                    for item in (
                        '请填写分组字段',
                        '请至少添加一条变量对应规则',
                    )
                )
                or any('缂哄皯' in item for item in issues)
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
        if self._is_placeholder_group_rule(
            source_value=source_value,
            target_conversation_name=target_conversation_name,
        ):
            raise BroadcastError(
                BROADCAST_GROUP_RULE_REGEX_INVALID,
                '群规则无效：请填写真实用户名和真实目标群名称，不能保存占位历史规则。',
            )
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

    def _serialize_group_rule(self, row) -> dict[str, Any]:
        payload = self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastGroupRule, row)
        invalid_legacy = self._is_placeholder_group_rule(
            source_value=str(row.source_value or ''),
            target_conversation_name=str(row.target_conversation_name or ''),
        )
        payload['invalid_legacy'] = invalid_legacy
        payload['invalid_reason'] = '无效历史规则，不参与匹配。' if invalid_legacy else None
        return payload

    def _is_placeholder_group_rule(self, *, source_value: str, target_conversation_name: str) -> bool:
        normalized_source = str(source_value or '').strip()
        normalized_target = str(target_conversation_name or '').strip()
        return (
            not normalized_source
            or not normalized_target
            or normalized_source == '??'
            or normalized_target == '??'
        )

    def _iter_matchable_group_rules(self, rows: list[Any]) -> list[Any]:
        return [
            row
            for row in rows
            if not self._is_placeholder_group_rule(
                source_value=str(getattr(row, 'source_value', '') or ''),
                target_conversation_name=str(getattr(row, 'target_conversation_name', '') or ''),
            )
        ]

    async def _validate_group_rule_target(
        self,
        scope: dict[str, str],
        target_conversation_name: str,
    ) -> None:
        normalized_target = str(target_conversation_name or '').strip()
        if not normalized_target:
            raise BroadcastError(BROADCAST_GROUP_RULE_REGEX_INVALID)

        group_names = await self.repository.list_group_names(**scope)
        if not group_names:
            return

        exists = any(str(item.name or '') == normalized_target for item in group_names)
        if not exists:
            raise BroadcastError(
                BROADCAST_GROUP_RULE_REGEX_INVALID,
                '目标群不存在，或不属于当前 Bot / Connector。',
            )

    def _serialize_template(self, row) -> dict[str, Any]:
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastTemplate, row)

    async def _serialize_draft(self, row) -> dict[str, Any]:
        data = self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastDraft, row)
        batch = await self.repository.get_import_batch(
            int(row.import_batch_id),
            bot_uuid=str(row.bot_uuid),
            connector_id=str(row.connector_id),
        )
        data['drafts_stale'] = bool(batch.drafts_stale) if batch is not None else False
        return data

    async def _assert_draft_ready_for_execution(self, draft, scope: dict[str, str]) -> None:
        if str(draft.status) != 'ready':
            raise BroadcastError(BROADCAST_EXECUTION_DRAFT_NOT_READY, '浠?ready 鑽夌鍏佽鎵ц')
        if not str(draft.target_conversation_name or '').strip():
            raise BroadcastError(BROADCAST_EXECUTION_DRAFT_NOT_READY, '鐩爣缇よ亰涓嶈兘涓虹┖')
        if not str(draft.draft_text or '').strip():
            raise BroadcastError(BROADCAST_EXECUTION_DRAFT_NOT_READY, '鑽夌姝ｆ枃涓嶈兘涓虹┖')
        batch = await self.repository.get_import_batch(int(draft.import_batch_id), **scope)
        if batch is None:
            raise BroadcastError(BROADCAST_IMPORT_NOT_FOUND, '瀵煎叆鎵规涓嶅瓨鍦ㄦ垨宸茶鍒犻櫎')
        if bool(batch.drafts_stale):
            raise BroadcastError(BROADCAST_EXECUTION_DRAFT_STALE, '当前草稿已过期，请重新生成草稿后再执行。')

    async def _transition_execution_batch_to_queued(
        self,
        batch_id: int,
        scope: dict[str, Any],
        payload: dict[str, Any],
        *,
        allowed_statuses: set[str],
    ) -> dict[str, Any]:
        validated_scope = await self.validate_scope(scope)
        batch = await self.repository.get_execution_batch(batch_id, **validated_scope)
        if batch is None:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_NOT_FOUND, '执行批次不存在或已被删除')
        if str(batch.mode) != 'paste_only':
            raise BroadcastError(BROADCAST_EXECUTION_MODE_INVALID, '只有 paste_only 批次允许进入 Worker 队列')
        if str(batch.status) not in allowed_statuses:
            raise BroadcastError(BROADCAST_EXECUTION_BATCH_STATUS_INVALID, '当前批次状态不允许启动或继续')

        operator = str(payload.get('operator') or '').strip() or 'unknown'
        async with self.ap.persistence_mgr.get_db_engine().begin() as conn:
            updated = await self.repository.update_execution_batch(
                batch_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                updates={
                    'status': 'queued',
                    'paused_at': None,
                    'last_action_by': operator,
                },
                conn=conn,
            )
            await self.repository.recompute_execution_batch_counts(
                batch_id,
                bot_uuid=validated_scope['bot_uuid'],
                connector_id=validated_scope['connector_id'],
                conn=conn,
            )
        self._wake_worker()
        return self._serialize_execution_batch(updated)

    def _get_runtime_gateway(self) -> BroadcastRuntimeGateway:
        return BroadcastRuntimeGateway(self.ap.desktop_automation_service)

    def _wake_worker(self) -> None:
        worker = getattr(self.ap, 'broadcast_execution_worker', None)
        if worker is not None:
            worker.wake()

    @staticmethod
    def _coerce_terminal_task_status(runtime_status: str) -> str:
        normalized = str(runtime_status or '').strip().lower()
        if normalized in {'succeeded', 'succeeded_with_warning'}:
            return 'succeeded'
        if normalized in {'timed_out', 'timeout', 'unknown', 'running', 'queued'}:
            return 'interrupted'
        if normalized in {'cancelled'}:
            return 'cancelled'
        return 'failed'

    def _is_send_enabled(self, scope: dict[str, Any]) -> bool:
        config_enabled = str(self.ap.instance_config.data.get('broadcast', {}).get('send_enabled', '0')) == '1'
        env_enabled = str(os.environ.get('LANGBOT_BROADCAST_SEND_ENABLED') or '0') == '1'
        return self._is_connector_send_allowed(scope) and (config_enabled or env_enabled)

    def _is_connector_send_allowed(self, scope: dict[str, Any]) -> bool:
        try:
            bindings = self.ap.instance_config.data.get('broadcast', {}).get('allow_send_connectors') or {}
            connector_id = str(scope.get('connector_id') or '')
            if connector_id in bindings:
                return bool(bindings.get(connector_id))
            env_list = str(os.environ.get('LANGBOT_BROADCAST_SEND_ALLOW_CONNECTORS') or '').strip()
            if not env_list:
                return False
            return connector_id in {item.strip() for item in env_list.split(',') if item.strip()}
        except Exception:
            return False

    def _assert_send_feature_enabled(self, scope: dict[str, Any]) -> None:
        if not self._is_send_enabled(scope):
            raise BroadcastError(BROADCAST_EXECUTION_SEND_DISABLED, '真实发送功能未开启')
    def _build_execution_request_digest(
        self,
        *,
        action: str,
        channel: str,
        target_conversation: str,
        draft_text: str,
    ) -> str:
        raw = action + '\0' + channel + '\0' + target_conversation + '\0' + draft_text
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def _serialize_execution_batch(self, row) -> dict[str, Any]:
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastExecutionBatch, row)

    def _serialize_execution_task(self, row) -> dict[str, Any]:
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastExecutionTask, row)

    def _serialize_execution_attempt(self, row) -> dict[str, Any]:
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastExecutionAttempt, row)

    def _serialize_execution_evidence(self, row) -> dict[str, Any]:
        return self.ap.persistence_mgr.serialize_model(persistence_broadcast.BroadcastExecutionEvidence, row)

    def _sanitize_runtime_result(self, runtime_result: dict[str, Any] | None) -> dict[str, Any] | None:
        if runtime_result is None:
            return None

        sanitized = dict(runtime_result)
        technical_details = sanitized.pop('technical_details', None)
        if technical_details is not None:
            sanitized['technical_details'] = self._sanitize_technical_details(technical_details)
        return sanitized

    def _sanitize_technical_details(self, technical_details: Any) -> dict[str, Any] | None:
        if not isinstance(technical_details, dict):
            return None

        redacted: dict[str, Any] = {}
        allowed_text_keys = {
            'runtime_task_id',
            'stage',
            'status',
            'error_code',
            'verification_method',
            'verification_error_code',
            'expected_digest',
            'actual_digest',
        }

        for key, value in technical_details.items():
            lowered = str(key).lower()
            if lowered in {'authorization', 'token', 'cookie', 'drafttext', 'draft_text'}:
                continue
            if 'path' in lowered:
                continue
            if key in allowed_text_keys or isinstance(value, (int, float, bool)) or value is None:
                redacted[key] = value
        return redacted or None

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

    def _map_import_processor_error(self, exc: BroadcastImportProcessorError) -> BroadcastError:
        if exc.message.startswith('导入文件缺少以下字段：'):
            return BroadcastError(BROADCAST_IMPORT_FIELDS_MISSING, exc.message)
        if exc.message.startswith('褰撳墠瀵煎叆鏁版嵁缂哄皯浠ヤ笅瀛楁锛屾棤娉曢噸鏂板尮閰嶏細'):
            return BroadcastError(BROADCAST_IMPORT_REMATCH_FIELDS_MISSING, exc.message)
        if exc.message == '璇峰厛璁剧疆瀹㈡埛鍒嗙粍瀛楁鍚庡啀瀵煎叆鏂囦欢':
            return BroadcastError(BROADCAST_IMPORT_GROUP_FIELD_REQUIRED, exc.message)
        return BroadcastError(BROADCAST_IMPORT_FILE_INVALID, exc.message)

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
