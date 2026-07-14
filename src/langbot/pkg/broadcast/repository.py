from __future__ import annotations

import asyncio
from typing import Any

import sqlalchemy

from ..entity.persistence import broadcast as persistence_broadcast
from ..entity.persistence import database_mode as persistence_database_mode


class BroadcastRepository:
    _execution_claim_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, persistence_mgr) -> None:
        self.persistence_mgr = persistence_mgr

    @staticmethod
    def _scoped_import_batch_ids(import_batch_id: int, *, bot_uuid: str, connector_id: str):
        return sqlalchemy.select(persistence_broadcast.BroadcastImportBatch.id).where(
            persistence_broadcast.BroadcastImportBatch.id == import_batch_id,
            persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
            persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
        )

    @staticmethod
    def _scoped_execution_batch_ids(execution_batch_id: int, *, bot_uuid: str, connector_id: str):
        return sqlalchemy.select(persistence_broadcast.BroadcastExecutionBatch.id).where(
            persistence_broadcast.BroadcastExecutionBatch.id == execution_batch_id,
            persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
            persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
        )

    @staticmethod
    def _group_value_token_expr():
        return sqlalchemy.func.coalesce(
            persistence_broadcast.BroadcastImportRow.group_value,
            sqlalchemy.literal('__invalid__'),
        )

    @staticmethod
    def _order_value_expr(source_field: str | None):
        if not source_field:
            return sqlalchemy.literal(None)
        raw_value = persistence_broadcast.BroadcastImportRow.raw_data[source_field].as_string()
        return sqlalchemy.func.nullif(sqlalchemy.func.trim(sqlalchemy.func.coalesce(raw_value, '')), '')

    async def list_import_batches(self, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastImportBatch)
            .where(
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastImportBatch.created_at.desc(),
                persistence_broadcast.BroadcastImportBatch.id.desc(),
            )
        )
        return self._all_models(result)

    async def get_import_batch(self, import_batch_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastImportBatch).where(
                persistence_broadcast.BroadcastImportBatch.id == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def create_import_batch(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastImportBatch).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def update_import_batch(
        self,
        import_batch_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportBatch)
            .where(
                persistence_broadcast.BroadcastImportBatch.id == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_import_batch(import_batch_id, bot_uuid=bot_uuid, connector_id=connector_id, conn=conn)

    async def delete_import_batch(self, import_batch_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastImportRow).where(
                persistence_broadcast.BroadcastImportRow.import_batch_id.in_(
                    self._scoped_import_batch_ids(
                        import_batch_id,
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                    )
                ),
            ),
            conn=conn,
        )
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastImportGroupTemplateAssignment).where(
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.import_batch_id.in_(
                    self._scoped_import_batch_ids(
                        import_batch_id,
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                    )
                ),
            ),
            conn=conn,
        )
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastDraft).where(
                persistence_broadcast.BroadcastDraft.import_batch_id.in_(
                    self._scoped_import_batch_ids(
                        import_batch_id,
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                    )
                ),
            ),
            conn=conn,
        )
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastImportBatch).where(
                persistence_broadcast.BroadcastImportBatch.id == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def list_templates(self, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastTemplate)
            .where(
                persistence_broadcast.BroadcastTemplate.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastTemplate.connector_id == connector_id,
            )
            .order_by(persistence_broadcast.BroadcastTemplate.updated_at.desc(), persistence_broadcast.BroadcastTemplate.id.desc())
        )
        return self._all_models(result)

    async def get_template(self, template_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastTemplate).where(
                persistence_broadcast.BroadcastTemplate.id == template_id,
                persistence_broadcast.BroadcastTemplate.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastTemplate.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def create_template(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastTemplate).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def update_template(
        self,
        template_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastTemplate)
            .where(
                persistence_broadcast.BroadcastTemplate.id == template_id,
                persistence_broadcast.BroadcastTemplate.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastTemplate.connector_id == connector_id,
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_template(template_id, bot_uuid=bot_uuid, connector_id=connector_id, conn=conn)

    async def delete_template(self, template_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
        await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportGroupTemplateAssignment)
            .where(
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.template_id == template_id,
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.import_batch_id.in_(
                    sqlalchemy.select(persistence_broadcast.BroadcastImportBatch.id).where(
                        persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                        persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
                    )
                ),
            )
            .values({'template_id': None}),
            conn=conn,
        )
        await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastDraft)
            .where(
                persistence_broadcast.BroadcastDraft.template_id == template_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            )
            .values({'template_id': None}),
            conn=conn,
        )
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastTemplate).where(
                persistence_broadcast.BroadcastTemplate.id == template_id,
                persistence_broadcast.BroadcastTemplate.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastTemplate.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def get_variable_profile(self, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastVariableProfile).where(
                persistence_broadcast.BroadcastVariableProfile.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastVariableProfile.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def upsert_variable_profile(self, conn, payload: dict[str, Any]) -> int:
        existing = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastVariableProfile.id).where(
                persistence_broadcast.BroadcastVariableProfile.bot_uuid == payload['bot_uuid'],
                persistence_broadcast.BroadcastVariableProfile.connector_id == payload['connector_id'],
            ),
            conn=conn,
        )
        existing_id = existing.scalar()
        if existing_id is not None:
            await self.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastVariableProfile)
                .where(persistence_broadcast.BroadcastVariableProfile.id == existing_id)
                .values(
                    {
                        'group_field': payload.get('group_field'),
                        'mapping_rules': payload['mapping_rules'],
                    }
                ),
                conn=conn,
            )
            return int(existing_id)

        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastVariableProfile).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def list_group_rules(self, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupRule)
            .where(
                persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastGroupRule.priority.desc(),
                persistence_broadcast.BroadcastGroupRule.id.desc(),
            ),
            conn=conn,
        )
        return self._all_models(result)

    async def get_group_rule(self, rule_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupRule).where(
                persistence_broadcast.BroadcastGroupRule.id == rule_id,
                persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def find_duplicate_exact_rules(
        self,
        *,
        bot_uuid: str,
        connector_id: str,
        normalized_source_value: str,
        normalized_match_expression: str,
        exclude_rule_id: int | None = None,
        conn=None,
    ):
        normalized_source_expr = sqlalchemy.func.trim(
            sqlalchemy.func.coalesce(persistence_broadcast.BroadcastGroupRule.source_value, '')
        )
        normalized_expression_expr = sqlalchemy.func.trim(
            sqlalchemy.func.coalesce(persistence_broadcast.BroadcastGroupRule.match_expression, '')
        )
        normalized_target_expr = sqlalchemy.func.trim(
            sqlalchemy.func.coalesce(persistence_broadcast.BroadcastGroupRule.target_conversation_name, '')
        )
        conditions = [
            persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
            persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            persistence_broadcast.BroadcastGroupRule.match_type == 'exact',
            persistence_broadcast.BroadcastGroupRule.enabled.is_(True),
            normalized_source_expr == normalized_source_value,
            normalized_expression_expr == normalized_match_expression,
            normalized_source_expr != '',
            normalized_source_expr != '??',
            normalized_target_expr != '',
            normalized_target_expr != '??',
        ]
        if exclude_rule_id is not None:
            conditions.append(persistence_broadcast.BroadcastGroupRule.id != exclude_rule_id)

        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupRule)
            .where(*conditions)
            .order_by(
                persistence_broadcast.BroadcastGroupRule.priority.desc(),
                persistence_broadcast.BroadcastGroupRule.id.asc(),
            ),
            conn=conn,
        )
        return self._all_models(result)

    async def create_group_rule(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupRule).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def update_group_rule(
        self,
        rule_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastGroupRule)
            .where(
                persistence_broadcast.BroadcastGroupRule.id == rule_id,
                persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_group_rule(rule_id, bot_uuid=bot_uuid, connector_id=connector_id, conn=conn)

    async def delete_group_rule(self, rule_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
        await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportRow)
            .where(
                persistence_broadcast.BroadcastImportRow.matched_rule_id == rule_id,
                persistence_broadcast.BroadcastImportRow.import_batch_id.in_(
                    sqlalchemy.select(persistence_broadcast.BroadcastImportBatch.id).where(
                        persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                        persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
                    )
                ),
            )
            .values({'matched_rule_id': None}),
            conn=conn,
        )
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastGroupRule).where(
                persistence_broadcast.BroadcastGroupRule.id == rule_id,
                persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def list_group_names(self, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupName)
            .where(
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
            )
            .order_by(persistence_broadcast.BroadcastGroupName.name.asc(), persistence_broadcast.BroadcastGroupName.id.asc())
            ,
            conn=conn,
        )
        return self._all_models(result)

    async def get_group_name_by_external_conversation_id(
        self,
        *,
        bot_uuid: str,
        connector_id: str,
        external_conversation_id: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupName).where(
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
                persistence_broadcast.BroadcastGroupName.external_conversation_id == external_conversation_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def get_group_name_by_name(
        self,
        *,
        bot_uuid: str,
        connector_id: str,
        name: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupName).where(
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
                persistence_broadcast.BroadcastGroupName.name == name,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def list_group_names_by_name(
        self,
        *,
        bot_uuid: str,
        connector_id: str,
        name: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupName)
            .where(
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
                persistence_broadcast.BroadcastGroupName.name == name,
            )
            .order_by(persistence_broadcast.BroadcastGroupName.id.asc()),
            conn=conn,
        )
        return self._all_models(result)

    async def update_group_name(
        self,
        group_name_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastGroupName)
            .where(
                persistence_broadcast.BroadcastGroupName.id == group_name_id,
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        follow_up = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupName).where(
                persistence_broadcast.BroadcastGroupName.id == group_name_id,
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(follow_up)

    async def create_group_name(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def list_database_conversations_for_group_sync(
        self,
        *,
        connector_id: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_database_mode.DatabaseConversation).where(
                persistence_database_mode.DatabaseConversation.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._all_models(result)

    async def delete_group_name(self, group_name_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastGroupName).where(
                persistence_broadcast.BroadcastGroupName.id == group_name_id,
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def replace_import_rows(self, conn, *, import_batch_id: int, rows: list[dict[str, Any]]) -> None:
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastImportRow).where(
                persistence_broadcast.BroadcastImportRow.import_batch_id == import_batch_id,
            ),
            conn=conn,
        )
        if not rows:
            return
        await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastImportRow).values(
                [{**row, 'import_batch_id': import_batch_id} for row in rows]
            ),
            conn=conn,
        )

    async def list_import_rows(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        match_status: str | None = None,
        keyword: str | None = None,
        page: int | None = None,
        page_size: int | None = None,
        conn=None,
    ):
        stmt = (
            sqlalchemy.select(persistence_broadcast.BroadcastImportRow)
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id == persistence_broadcast.BroadcastImportRow.import_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastImportRow.import_batch_id == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            )
            .order_by(persistence_broadcast.BroadcastImportRow.source_row_number.asc())
        )
        if match_status:
            stmt = stmt.where(persistence_broadcast.BroadcastImportRow.match_status == match_status)
        if keyword:
            like_value = f'%{keyword}%'
            stmt = stmt.where(
                sqlalchemy.or_(
                    persistence_broadcast.BroadcastImportRow.group_value.ilike(like_value),
                    persistence_broadcast.BroadcastImportRow.matched_conversation_name.ilike(like_value),
                )
            )
        if page and page_size:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.persistence_mgr.execute_async(stmt, conn=conn)
        return self._all_models(result)

    async def count_import_rows(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        match_status: str | None = None,
        keyword: str | None = None,
    ) -> int:
        stmt = (
            sqlalchemy.select(sqlalchemy.func.count())
            .select_from(persistence_broadcast.BroadcastImportRow)
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id == persistence_broadcast.BroadcastImportRow.import_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastImportRow.import_batch_id == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            )
        )
        if match_status:
            stmt = stmt.where(persistence_broadcast.BroadcastImportRow.match_status == match_status)
        if keyword:
            like_value = f'%{keyword}%'
            stmt = stmt.where(
                sqlalchemy.or_(
                    persistence_broadcast.BroadcastImportRow.group_value.ilike(like_value),
                    persistence_broadcast.BroadcastImportRow.matched_conversation_name.ilike(like_value),
                )
            )
        result = await self.persistence_mgr.execute_async(stmt)
        return int(result.scalar_one() or 0)

    async def update_import_row_match_result(
        self,
        import_row_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastImportRow)
            .where(
                persistence_broadcast.BroadcastImportRow.id == import_row_id,
                persistence_broadcast.BroadcastImportRow.import_batch_id.in_(
                    self._scoped_import_batch_ids(
                        sqlalchemy.select(persistence_broadcast.BroadcastImportRow.import_batch_id)
                        .where(persistence_broadcast.BroadcastImportRow.id == import_row_id)
                        .scalar_subquery(),
                        bot_uuid=bot_uuid,
                        connector_id=connector_id,
                    )
                ),
            )
            .values(updates),
            conn=conn,
        )
        return bool(result.rowcount)

    async def create_import_group_template_assignment(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastImportGroupTemplateAssignment).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def list_import_group_template_assignments(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastImportGroupTemplateAssignment)
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id
                == persistence_broadcast.BroadcastImportGroupTemplateAssignment.import_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.import_batch_id == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.group_key.asc(),
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.id.asc(),
            ),
            conn=conn,
        )
        return self._all_models(result)

    async def delete_import_group_template_assignment(
        self,
        conn,
        *,
        import_batch_id: int,
        group_key: str,
    ) -> bool:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastImportGroupTemplateAssignment).where(
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.import_batch_id == import_batch_id,
                persistence_broadcast.BroadcastImportGroupTemplateAssignment.group_key == group_key,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def upsert_import_group_template_assignments(
        self,
        conn,
        *,
        import_batch_id: int,
        items: list[dict[str, Any]],
    ) -> None:
        for item in items:
            existing = await self.persistence_mgr.execute_async(
                sqlalchemy.select(persistence_broadcast.BroadcastImportGroupTemplateAssignment.id).where(
                    persistence_broadcast.BroadcastImportGroupTemplateAssignment.import_batch_id == import_batch_id,
                    persistence_broadcast.BroadcastImportGroupTemplateAssignment.group_key == item['group_key'],
                ),
                conn=conn,
            )
            existing_id = existing.scalar()
            payload = {
                'import_batch_id': import_batch_id,
                'group_key': item['group_key'],
                'template_id': item.get('template_id'),
            }
            if existing_id is None:
                await self.persistence_mgr.execute_async(
                    sqlalchemy.insert(persistence_broadcast.BroadcastImportGroupTemplateAssignment).values(payload),
                    conn=conn,
                )
            else:
                await self.persistence_mgr.execute_async(
                    sqlalchemy.update(persistence_broadcast.BroadcastImportGroupTemplateAssignment)
                    .where(persistence_broadcast.BroadcastImportGroupTemplateAssignment.id == existing_id)
                    .values(payload),
                    conn=conn,
                )

    async def get_draft_by_group_value(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        group_value: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastDraft).where(
                persistence_broadcast.BroadcastDraft.import_batch_id == import_batch_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
                persistence_broadcast.BroadcastDraft.group_value == group_value,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def create_draft(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastDraft).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    def _build_import_group_summary_stmt(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        order_number_source_field: str | None,
        keyword: str | None = None,
    ):
        order_value_expr = self._order_value_expr(order_number_source_field)
        matched_conversation_id_expr = sqlalchemy.func.nullif(
            sqlalchemy.func.trim(
                sqlalchemy.func.coalesce(
                    persistence_broadcast.BroadcastImportRow.matched_conversation_id,
                    '',
                )
            ),
            '',
        )
        matched_conversation_expr = sqlalchemy.func.nullif(
            sqlalchemy.func.trim(
                sqlalchemy.func.coalesce(
                    persistence_broadcast.BroadcastImportRow.matched_conversation_name,
                    '',
                )
            ),
            '',
        )
        stmt = (
            sqlalchemy.select(
                persistence_broadcast.BroadcastImportRow.group_value.label('group_value'),
                sqlalchemy.func.min(
                    persistence_broadcast.BroadcastImportRow.source_row_number
                ).label('first_source_row_number'),
                sqlalchemy.func.count(
                    persistence_broadcast.BroadcastImportRow.id
                ).label('raw_row_count'),
                sqlalchemy.func.count(
                    sqlalchemy.distinct(order_value_expr)
                ).label('distinct_order_number_count'),
                sqlalchemy.func.min(
                    persistence_broadcast.BroadcastImportRow.match_status
                ).label('single_match_status'),
                sqlalchemy.func.count(
                    sqlalchemy.distinct(
                        persistence_broadcast.BroadcastImportRow.match_status
                    )
                ).label('match_status_count'),
                sqlalchemy.func.min(
                    matched_conversation_id_expr
                ).label('matched_conversation_id'),
                sqlalchemy.func.min(
                    matched_conversation_expr
                ).label('matched_conversation_name'),
                sqlalchemy.func.count(
                    sqlalchemy.distinct(
                        sqlalchemy.func.coalesce(
                            matched_conversation_id_expr,
                            matched_conversation_expr,
                        )
                    )
                ).label('matched_conversation_identity_count'),
                sqlalchemy.func.min(
                    persistence_broadcast.BroadcastImportRow.error_message
                ).label('first_error_message'),
            )
            .select_from(persistence_broadcast.BroadcastImportRow)
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id
                == persistence_broadcast.BroadcastImportRow.import_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastImportRow.import_batch_id
                == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id
                == connector_id,
            )
            .group_by(persistence_broadcast.BroadcastImportRow.group_value)
        )
        if keyword:
            like_value = f'%{keyword}%'
            stmt = stmt.where(
                sqlalchemy.or_(
                    persistence_broadcast.BroadcastImportRow.group_value.ilike(
                        like_value
                    ),
                    persistence_broadcast.BroadcastImportRow.matched_conversation_name.ilike(
                        like_value
                    ),
                )
            )
        return stmt

    async def list_import_group_summaries(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        order_number_source_field: str | None,
        page: int | None = None,
        page_size: int | None = None,
        keyword: str | None = None,
        conn=None,
    ) -> list[dict[str, Any]]:
        stmt = self._build_import_group_summary_stmt(
            import_batch_id=import_batch_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            order_number_source_field=order_number_source_field,
            keyword=keyword,
        ).order_by(
            sqlalchemy.asc(sqlalchemy.literal_column('first_source_row_number')),
            sqlalchemy.asc(sqlalchemy.func.coalesce(sqlalchemy.literal_column('group_value'), '')),
        )
        if page and page_size:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.persistence_mgr.execute_async(stmt, conn=conn)
        return [dict(row._mapping) for row in result.all()]

    async def list_all_import_group_summaries(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        order_number_source_field: str | None,
        keyword: str | None = None,
        conn=None,
    ) -> list[dict[str, Any]]:
        result = await self.persistence_mgr.execute_async(
            self._build_import_group_summary_stmt(
                import_batch_id=import_batch_id,
                bot_uuid=bot_uuid,
                connector_id=connector_id,
                order_number_source_field=order_number_source_field,
                keyword=keyword,
            ),
            conn=conn,
        )
        return [dict(row._mapping) for row in result.all()]

    async def count_import_groups(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        order_number_source_field: str | None,
        keyword: str | None = None,
        conn=None,
    ) -> int:
        subquery = self._build_import_group_summary_stmt(
            import_batch_id=import_batch_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            order_number_source_field=order_number_source_field,
            keyword=keyword,
        ).subquery()
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count()).select_from(subquery),
            conn=conn,
        )
        return int(result.scalar_one() or 0)

    async def list_import_rows_for_group(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        group_value: str | None,
        page: int | None = None,
        page_size: int | None = None,
        conn=None,
    ):
        stmt = (
            sqlalchemy.select(persistence_broadcast.BroadcastImportRow)
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id
                == persistence_broadcast.BroadcastImportRow.import_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastImportRow.import_batch_id
                == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id
                == connector_id,
                persistence_broadcast.BroadcastImportRow.group_value.is_(None)
                if group_value is None
                else persistence_broadcast.BroadcastImportRow.group_value
                == group_value,
            )
            .order_by(
                persistence_broadcast.BroadcastImportRow.source_row_number.asc()
            )
        )
        if page and page_size:
            stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await self.persistence_mgr.execute_async(stmt, conn=conn)
        return self._all_models(result)

    async def count_import_rows_for_group(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        group_value: str | None,
        conn=None,
    ) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count())
            .select_from(persistence_broadcast.BroadcastImportRow)
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id
                == persistence_broadcast.BroadcastImportRow.import_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastImportRow.import_batch_id
                == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id
                == connector_id,
                persistence_broadcast.BroadcastImportRow.group_value.is_(None)
                if group_value is None
                else persistence_broadcast.BroadcastImportRow.group_value
                == group_value,
            ),
            conn=conn,
        )
        return int(result.scalar_one() or 0)

    async def replace_drafts(
        self,
        conn,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        drafts: list[dict[str, Any]],
    ) -> None:
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastDraft).where(
                persistence_broadcast.BroadcastDraft.import_batch_id == import_batch_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            ),
            conn=conn,
        )
        if not drafts:
            return
        await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastDraft).values(drafts),
            conn=conn,
        )

    async def list_drafts(
        self,
        *,
        bot_uuid: str,
        connector_id: str,
        import_batch_id: int | None = None,
        status: str | None = None,
        send_status: str | None = None,
        exclude_invalid: bool = False,
        keyword: str | None = None,
        conn=None,
    ):
        stmt = sqlalchemy.select(persistence_broadcast.BroadcastDraft).where(
            persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
            persistence_broadcast.BroadcastDraft.connector_id == connector_id,
        )
        if import_batch_id is not None:
            stmt = stmt.where(persistence_broadcast.BroadcastDraft.import_batch_id == import_batch_id)
        if status:
            stmt = stmt.where(persistence_broadcast.BroadcastDraft.status == status)
        if send_status:
            stmt = stmt.where(
                sqlalchemy.func.coalesce(
                    persistence_broadcast.BroadcastDraft.send_status,
                    'pending',
                )
                == send_status
            )
        if exclude_invalid:
            stmt = stmt.where(persistence_broadcast.BroadcastDraft.status != 'invalid')
        if keyword:
            like_value = f'%{keyword}%'
            stmt = stmt.where(
                sqlalchemy.or_(
                    persistence_broadcast.BroadcastDraft.group_value.ilike(like_value),
                    persistence_broadcast.BroadcastDraft.target_conversation_name.ilike(like_value),
                    persistence_broadcast.BroadcastDraft.draft_text.ilike(like_value),
                )
            )
        stmt = stmt.order_by(
            persistence_broadcast.BroadcastDraft.created_at.asc(),
            persistence_broadcast.BroadcastDraft.id.asc(),
        )
        result = await self.persistence_mgr.execute_async(stmt, conn=conn)
        return self._all_models(result)

    async def get_draft(self, draft_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastDraft).where(
                persistence_broadcast.BroadcastDraft.id == draft_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def update_draft(
        self,
        draft_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastDraft)
            .where(
                persistence_broadcast.BroadcastDraft.id == draft_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_draft(draft_id, bot_uuid=bot_uuid, connector_id=connector_id, conn=conn)

    async def delete_draft(self, draft_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastDraft).where(
                persistence_broadcast.BroadcastDraft.id == draft_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def create_attachment_asset(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastAttachmentAsset).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def get_attachment_asset(
        self,
        asset_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastAttachmentAsset).where(
                persistence_broadcast.BroadcastAttachmentAsset.id == asset_id,
                persistence_broadcast.BroadcastAttachmentAsset.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastAttachmentAsset.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def delete_attachment_asset(
        self,
        asset_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ) -> bool:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastAttachmentAsset).where(
                persistence_broadcast.BroadcastAttachmentAsset.id == asset_id,
                persistence_broadcast.BroadcastAttachmentAsset.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastAttachmentAsset.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    async def list_import_group_attachments(
        self,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        group_key: str | None = None,
        conn=None,
    ) -> list[dict[str, Any]]:
        stmt = (
            sqlalchemy.select(
                persistence_broadcast.BroadcastImportGroupAttachment.id.label('relation_id'),
                persistence_broadcast.BroadcastImportGroupAttachment.group_key.label('group_key'),
                persistence_broadcast.BroadcastImportGroupAttachment.group_value_snapshot.label('group_value_snapshot'),
                persistence_broadcast.BroadcastImportGroupAttachment.sort_order.label('sort_order'),
                persistence_broadcast.BroadcastAttachmentAsset.id.label('asset_id'),
                persistence_broadcast.BroadcastAttachmentAsset.original_name.label('original_name'),
                persistence_broadcast.BroadcastAttachmentAsset.stored_name.label('stored_name'),
                persistence_broadcast.BroadcastAttachmentAsset.stored_path.label('stored_path'),
                persistence_broadcast.BroadcastAttachmentAsset.relative_path.label('relative_path'),
                persistence_broadcast.BroadcastAttachmentAsset.size_bytes.label('size_bytes'),
                persistence_broadcast.BroadcastAttachmentAsset.sha256.label('sha256'),
                persistence_broadcast.BroadcastAttachmentAsset.extension.label('extension'),
                persistence_broadcast.BroadcastAttachmentAsset.mime_type.label('mime_type'),
            )
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id
                == persistence_broadcast.BroadcastImportGroupAttachment.batch_id,
            )
            .join(
                persistence_broadcast.BroadcastAttachmentAsset,
                persistence_broadcast.BroadcastAttachmentAsset.id
                == persistence_broadcast.BroadcastImportGroupAttachment.attachment_asset_id,
            )
            .where(
                persistence_broadcast.BroadcastImportGroupAttachment.batch_id
                == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id
                == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastImportGroupAttachment.sort_order.asc(),
                persistence_broadcast.BroadcastImportGroupAttachment.id.asc(),
            )
        )
        if group_key is not None:
            stmt = stmt.where(
                persistence_broadcast.BroadcastImportGroupAttachment.group_key
                == group_key
            )
        result = await self.persistence_mgr.execute_async(stmt, conn=conn)
        return [dict(row._mapping) for row in result.all()]

    async def create_import_group_attachment(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastImportGroupAttachment).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def delete_import_group_attachment(
        self,
        attachment_relation_id: int,
        *,
        import_batch_id: int,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ) -> dict[str, Any] | None:
        relation = await self.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_broadcast.BroadcastImportGroupAttachment,
                persistence_broadcast.BroadcastAttachmentAsset.id.label('asset_id'),
            )
            .join(
                persistence_broadcast.BroadcastImportBatch,
                persistence_broadcast.BroadcastImportBatch.id
                == persistence_broadcast.BroadcastImportGroupAttachment.batch_id,
            )
            .join(
                persistence_broadcast.BroadcastAttachmentAsset,
                persistence_broadcast.BroadcastAttachmentAsset.id
                == persistence_broadcast.BroadcastImportGroupAttachment.attachment_asset_id,
            )
            .where(
                persistence_broadcast.BroadcastImportGroupAttachment.id
                == attachment_relation_id,
                persistence_broadcast.BroadcastImportGroupAttachment.batch_id
                == import_batch_id,
                persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastImportBatch.connector_id
                == connector_id,
            ),
            conn=conn,
        )
        row = relation.first()
        if row is None:
            return None
        mapping = dict(row._mapping)
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastImportGroupAttachment).where(
                persistence_broadcast.BroadcastImportGroupAttachment.id
                == attachment_relation_id
            ),
            conn=conn,
        )
        return mapping

    async def list_draft_attachments(
        self,
        draft_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ) -> list[dict[str, Any]]:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_broadcast.BroadcastDraftAttachment.id.label('relation_id'),
                persistence_broadcast.BroadcastDraftAttachment.draft_id.label('draft_id'),
                persistence_broadcast.BroadcastDraftAttachment.attachment_asset_id.label('attachment_asset_id'),
                persistence_broadcast.BroadcastDraftAttachment.original_name_snapshot.label('original_name_snapshot'),
                persistence_broadcast.BroadcastDraftAttachment.size_bytes_snapshot.label('size_bytes_snapshot'),
                persistence_broadcast.BroadcastDraftAttachment.sha256_snapshot.label('sha256_snapshot'),
                persistence_broadcast.BroadcastDraftAttachment.sort_order.label('sort_order'),
                persistence_broadcast.BroadcastAttachmentAsset.id.label('asset_id'),
                persistence_broadcast.BroadcastAttachmentAsset.original_name.label('original_name'),
                persistence_broadcast.BroadcastAttachmentAsset.stored_name.label('stored_name'),
                persistence_broadcast.BroadcastAttachmentAsset.stored_path.label('stored_path'),
                persistence_broadcast.BroadcastAttachmentAsset.relative_path.label('relative_path'),
                persistence_broadcast.BroadcastAttachmentAsset.size_bytes.label('size_bytes'),
                persistence_broadcast.BroadcastAttachmentAsset.sha256.label('sha256'),
                persistence_broadcast.BroadcastAttachmentAsset.extension.label('extension'),
                persistence_broadcast.BroadcastAttachmentAsset.mime_type.label('mime_type'),
            )
            .join(
                persistence_broadcast.BroadcastDraft,
                persistence_broadcast.BroadcastDraft.id
                == persistence_broadcast.BroadcastDraftAttachment.draft_id,
            )
            .join(
                persistence_broadcast.BroadcastAttachmentAsset,
                persistence_broadcast.BroadcastAttachmentAsset.id
                == persistence_broadcast.BroadcastDraftAttachment.attachment_asset_id,
            )
            .where(
                persistence_broadcast.BroadcastDraftAttachment.draft_id == draft_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastDraftAttachment.sort_order.asc(),
                persistence_broadcast.BroadcastDraftAttachment.id.asc(),
            ),
            conn=conn,
        )
        return [dict(row._mapping) for row in result.all()]

    async def create_draft_attachment(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastDraftAttachment).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def replace_draft_attachments(self, conn, *, draft_id: int, attachments: list[dict[str, Any]]) -> None:
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastDraftAttachment).where(
                persistence_broadcast.BroadcastDraftAttachment.draft_id == draft_id,
            ),
            conn=conn,
        )
        if not attachments:
            return
        await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastDraftAttachment).values(attachments),
            conn=conn,
        )

    async def delete_draft_attachment(
        self,
        relation_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ) -> dict[str, Any] | None:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_broadcast.BroadcastDraftAttachment,
                persistence_broadcast.BroadcastAttachmentAsset.id.label('asset_id'),
            )
            .join(
                persistence_broadcast.BroadcastDraft,
                persistence_broadcast.BroadcastDraft.id
                == persistence_broadcast.BroadcastDraftAttachment.draft_id,
            )
            .join(
                persistence_broadcast.BroadcastAttachmentAsset,
                persistence_broadcast.BroadcastAttachmentAsset.id
                == persistence_broadcast.BroadcastDraftAttachment.attachment_asset_id,
            )
            .where(
                persistence_broadcast.BroadcastDraftAttachment.id == relation_id,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            ),
            conn=conn,
        )
        row = result.first()
        if row is None:
            return None
        mapping = dict(row._mapping)
        await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastDraftAttachment).where(
                persistence_broadcast.BroadcastDraftAttachment.id == relation_id
            ),
            conn=conn,
        )
        return mapping

    async def list_execution_task_attachments(
        self,
        execution_task_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ) -> list[dict[str, Any]]:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_broadcast.BroadcastExecutionTaskAttachment.id.label('relation_id'),
                persistence_broadcast.BroadcastExecutionTaskAttachment.execution_task_id.label('execution_task_id'),
                persistence_broadcast.BroadcastExecutionTaskAttachment.attachment_asset_id.label('attachment_asset_id'),
                persistence_broadcast.BroadcastExecutionTaskAttachment.original_name_snapshot.label('original_name_snapshot'),
                persistence_broadcast.BroadcastExecutionTaskAttachment.size_bytes_snapshot.label('size_bytes_snapshot'),
                persistence_broadcast.BroadcastExecutionTaskAttachment.sha256_snapshot.label('sha256_snapshot'),
                persistence_broadcast.BroadcastExecutionTaskAttachment.sort_order.label('sort_order'),
                persistence_broadcast.BroadcastAttachmentAsset.id.label('asset_id'),
                persistence_broadcast.BroadcastAttachmentAsset.original_name.label('original_name'),
                persistence_broadcast.BroadcastAttachmentAsset.stored_name.label('stored_name'),
                persistence_broadcast.BroadcastAttachmentAsset.stored_path.label('stored_path'),
                persistence_broadcast.BroadcastAttachmentAsset.relative_path.label('relative_path'),
                persistence_broadcast.BroadcastAttachmentAsset.size_bytes.label('size_bytes'),
                persistence_broadcast.BroadcastAttachmentAsset.sha256.label('sha256'),
                persistence_broadcast.BroadcastAttachmentAsset.extension.label('extension'),
                persistence_broadcast.BroadcastAttachmentAsset.mime_type.label('mime_type'),
            )
            .join(
                persistence_broadcast.BroadcastExecutionTask,
                persistence_broadcast.BroadcastExecutionTask.id
                == persistence_broadcast.BroadcastExecutionTaskAttachment.execution_task_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .join(
                persistence_broadcast.BroadcastAttachmentAsset,
                persistence_broadcast.BroadcastAttachmentAsset.id
                == persistence_broadcast.BroadcastExecutionTaskAttachment.attachment_asset_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionTaskAttachment.execution_task_id
                == execution_task_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id
                == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastExecutionTaskAttachment.sort_order.asc(),
                persistence_broadcast.BroadcastExecutionTaskAttachment.id.asc(),
            ),
            conn=conn,
        )
        return [dict(row._mapping) for row in result.all()]

    async def create_execution_task_attachment(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastExecutionTaskAttachment).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def count_attachment_references(
        self,
        asset_id: int,
        *,
        conn=None,
    ) -> int:
        total = 0
        for model, field_name in [
            (persistence_broadcast.BroadcastImportGroupAttachment, 'attachment_asset_id'),
            (persistence_broadcast.BroadcastDraftAttachment, 'attachment_asset_id'),
            (persistence_broadcast.BroadcastExecutionTaskAttachment, 'attachment_asset_id'),
        ]:
            result = await self.persistence_mgr.execute_async(
                sqlalchemy.select(sqlalchemy.func.count())
                .select_from(model)
                .where(getattr(model, field_name) == asset_id),
                conn=conn,
            )
            total += int(result.scalar_one() or 0)
        return total

    async def update_draft_statuses(
        self,
        *,
        draft_ids: list[int],
        bot_uuid: str,
        connector_id: str,
        status: str,
        conn=None,
    ) -> int:
        unique_ids = list(dict.fromkeys(int(draft_id) for draft_id in draft_ids))
        if not unique_ids:
            return 0
        count_result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(sqlalchemy.func.count())
            .select_from(persistence_broadcast.BroadcastDraft)
            .where(
                persistence_broadcast.BroadcastDraft.id.in_(unique_ids),
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            ),
            conn=conn,
        )
        matched_count = int(count_result.scalar() or 0)
        if matched_count != len(unique_ids):
            return 0

        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastDraft)
            .where(
                persistence_broadcast.BroadcastDraft.id.in_(unique_ids),
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            )
            .values({'status': status}),
            conn=conn,
        )
        return int(result.rowcount or 0)

    async def update_drafts_attachment_stale(
        self,
        *,
        import_batch_id: int,
        group_value: str,
        bot_uuid: str,
        connector_id: str,
        attachments_stale: bool,
        conn=None,
    ) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastDraft)
            .where(
                persistence_broadcast.BroadcastDraft.import_batch_id
                == import_batch_id,
                persistence_broadcast.BroadcastDraft.group_value == group_value,
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
            )
            .values({'attachments_stale': attachments_stale}),
            conn=conn,
        )
        return int(result.rowcount or 0)

    async def update_draft_send_statuses(
        self,
        *,
        draft_ids: list[int],
        bot_uuid: str,
        connector_id: str,
        current_send_status: str,
        target_send_status: str,
        sent_at,
        conn=None,
    ) -> int:
        unique_ids = list(dict.fromkeys(int(draft_id) for draft_id in draft_ids))
        if not unique_ids:
            return 0
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastDraft)
            .where(
                persistence_broadcast.BroadcastDraft.id.in_(unique_ids),
                persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastDraft.connector_id == connector_id,
                persistence_broadcast.BroadcastDraft.status != 'invalid',
                sqlalchemy.func.coalesce(persistence_broadcast.BroadcastDraft.send_status, 'pending')
                == current_send_status,
            )
            .values(
                {
                    'send_status': target_send_status,
                    'sent_at': sent_at,
                }
            ),
            conn=conn,
        )
        return int(result.rowcount or 0)

    async def create_execution_batch(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastExecutionBatch).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def get_execution_batch(self, execution_batch_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionBatch).where(
                persistence_broadcast.BroadcastExecutionBatch.id == execution_batch_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def list_execution_batches(self, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionBatch)
            .where(
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastExecutionBatch.created_at.desc(),
                persistence_broadcast.BroadcastExecutionBatch.id.desc(),
            )
        )
        return self._all_models(result)

    async def list_execution_tasks(self, execution_batch_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionTask)
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionTask.execution_batch_id == execution_batch_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastExecutionTask.sequence_no.asc(),
                persistence_broadcast.BroadcastExecutionTask.id.asc(),
            ),
            conn=conn,
        )
        return self._all_models(result)

    async def create_execution_task(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastExecutionTask).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def get_execution_task(self, execution_task_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionTask)
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionTask.id == execution_task_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def get_active_send_task_for_draft(
        self,
        draft_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionTask)
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionTask.draft_id == draft_id,
                persistence_broadcast.BroadcastExecutionTask.action == 'send_message',
                persistence_broadcast.BroadcastExecutionTask.status.in_(('pending', 'running')),
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastExecutionTask.id.desc(),
            )
            .limit(1),
            conn=conn,
        )
        return self._first_model(result)

    async def update_execution_task(
        self,
        execution_task_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastExecutionTask)
            .where(
                persistence_broadcast.BroadcastExecutionTask.id == execution_task_id,
                persistence_broadcast.BroadcastExecutionTask.execution_batch_id.in_(
                    sqlalchemy.select(persistence_broadcast.BroadcastExecutionBatch.id).where(
                        persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                        persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
                    )
                ),
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_execution_task(
            execution_task_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            conn=conn,
        )

    async def create_execution_attempt(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastExecutionAttempt).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def get_execution_attempt(self, execution_attempt_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionAttempt)
            .join(
                persistence_broadcast.BroadcastExecutionTask,
                persistence_broadcast.BroadcastExecutionTask.id
                == persistence_broadcast.BroadcastExecutionAttempt.execution_task_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionAttempt.id == execution_attempt_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def list_execution_attempts(self, execution_task_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionAttempt)
            .join(
                persistence_broadcast.BroadcastExecutionTask,
                persistence_broadcast.BroadcastExecutionTask.id
                == persistence_broadcast.BroadcastExecutionAttempt.execution_task_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionAttempt.execution_task_id == execution_task_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            )
            .order_by(persistence_broadcast.BroadcastExecutionAttempt.attempt_no.asc()),
            conn=conn,
        )
        return self._all_models(result)

    async def update_execution_attempt(
        self,
        execution_attempt_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastExecutionAttempt)
            .where(
                persistence_broadcast.BroadcastExecutionAttempt.id == execution_attempt_id,
                persistence_broadcast.BroadcastExecutionAttempt.execution_task_id.in_(
                    sqlalchemy.select(persistence_broadcast.BroadcastExecutionTask.id)
                    .join(
                        persistence_broadcast.BroadcastExecutionBatch,
                        persistence_broadcast.BroadcastExecutionBatch.id
                        == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
                    )
                    .where(
                        persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                        persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
                    )
                ),
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_execution_attempt(
            execution_attempt_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            conn=conn,
        )

    async def create_execution_evidence(self, conn, payload: dict[str, Any]) -> int:
        existing = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionEvidence.id).where(
                persistence_broadcast.BroadcastExecutionEvidence.execution_attempt_id
                == payload['execution_attempt_id']
            ),
            conn=conn,
        )
        existing_id = existing.scalar()
        if existing_id is not None:
            await self.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastExecutionEvidence)
                .where(persistence_broadcast.BroadcastExecutionEvidence.id == existing_id)
                .values(payload),
                conn=conn,
            )
            return int(existing_id)
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastExecutionEvidence).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

    async def get_execution_evidence(self, execution_attempt_id: int, *, bot_uuid: str, connector_id: str, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionEvidence)
            .join(
                persistence_broadcast.BroadcastExecutionAttempt,
                persistence_broadcast.BroadcastExecutionAttempt.id
                == persistence_broadcast.BroadcastExecutionEvidence.execution_attempt_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionTask,
                persistence_broadcast.BroadcastExecutionTask.id
                == persistence_broadcast.BroadcastExecutionAttempt.execution_task_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionEvidence.execution_attempt_id == execution_attempt_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def update_execution_batch(
        self,
        execution_batch_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        updates: dict[str, Any],
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.update(persistence_broadcast.BroadcastExecutionBatch)
            .where(
                persistence_broadcast.BroadcastExecutionBatch.id == execution_batch_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            )
            .values(updates),
            conn=conn,
        )
        if not result.rowcount:
            return None
        return await self.get_execution_batch(
            execution_batch_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            conn=conn,
        )

    async def recompute_execution_batch_counts(
        self,
        execution_batch_id: int,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ):
        tasks = await self.list_execution_tasks(
            execution_batch_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            conn=conn,
        )
        batch = await self.get_execution_batch(
            execution_batch_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            conn=conn,
        )
        summary = {
            'total_tasks': len(tasks),
            'pending_tasks': 0,
            'running_tasks': 0,
            'succeeded_tasks': 0,
            'succeeded_with_warning_tasks': 0,
            'failed_tasks': 0,
            'cancelled_tasks': 0,
            'interrupted_tasks': 0,
        }
        for task in tasks:
            key = f'{str(task.status)}_tasks'
            if key in summary:
                summary[key] += 1

        total = summary['total_tasks']
        if total <= 0:
            status = 'created'
        elif summary['running_tasks'] > 0:
            status = 'running'
        elif summary['pending_tasks'] == total:
            current_status = str(batch.status) if batch is not None else 'created'
            status = current_status if current_status in {'queued', 'paused'} else 'created'
        elif summary['pending_tasks'] > 0:
            current_status = str(batch.status) if batch is not None else 'queued'
            status = 'paused' if current_status == 'paused' else 'queued'
        elif summary['succeeded_tasks'] + summary['succeeded_with_warning_tasks'] == total:
            status = 'completed'
        elif summary['cancelled_tasks'] == total:
            status = 'cancelled'
        elif (
            summary['failed_tasks'] > 0
            and summary['failed_tasks']
            + summary['succeeded_tasks']
            + summary['succeeded_with_warning_tasks']
            == total
        ):
            status = (
                'failed'
                if summary['succeeded_tasks'] == 0
                and summary['succeeded_with_warning_tasks'] == 0
                else 'partially_failed'
            )
        elif (
            summary['interrupted_tasks'] > 0
            and summary['interrupted_tasks']
            + summary['succeeded_tasks']
            + summary['succeeded_with_warning_tasks']
            == total
        ):
            status = (
                'interrupted'
                if summary['succeeded_tasks'] == 0
                and summary['succeeded_with_warning_tasks'] == 0
                else 'partially_failed'
            )
        else:
            status = 'partially_failed'

        summary.pop('succeeded_with_warning_tasks', None)
        has_active_tasks = summary['pending_tasks'] > 0 or summary['running_tasks'] > 0
        finished_candidates = [
            getattr(task, 'finished_at', None)
            for task in tasks
            if getattr(task, 'finished_at', None) is not None
        ]
        if has_active_tasks:
            finished_at = None
        elif batch is not None and getattr(batch, 'finished_at', None) is not None:
            finished_at = getattr(batch, 'finished_at', None)
        else:
            finished_at = max(finished_candidates) if finished_candidates else sqlalchemy.func.now()

        error_message = None
        if not has_active_tasks:
            interrupted_task = next(
                (
                    task
                    for task in tasks
                    if str(getattr(task, 'status', '') or '') == 'interrupted'
                ),
                None,
            )
            failed_task = next(
                (
                    task
                    for task in tasks
                    if str(getattr(task, 'status', '') or '') == 'failed'
                ),
                None,
            )
            cancelled_task = next(
                (
                    task
                    for task in tasks
                    if str(getattr(task, 'status', '') or '') == 'cancelled'
                ),
                None,
            )
            if interrupted_task is not None:
                error_message = (
                    str(getattr(interrupted_task, 'error_message', '') or '').strip()
                    or str(getattr(interrupted_task, 'error_code', '') or '').strip()
                    or 'Execution result requires manual review'
                )
            elif failed_task is not None:
                error_message = (
                    str(getattr(failed_task, 'error_message', '') or '').strip()
                    or str(getattr(failed_task, 'error_code', '') or '').strip()
                    or 'Execution failed'
                )
            elif cancelled_task is not None and status == 'cancelled':
                error_message = (
                    str(getattr(cancelled_task, 'error_message', '') or '').strip()
                    or str(getattr(cancelled_task, 'error_code', '') or '').strip()
                    or 'Execution cancelled'
                )

        return await self.update_execution_batch(
            execution_batch_id,
            bot_uuid=bot_uuid,
            connector_id=connector_id,
            updates={
                **summary,
                'status': status,
                'finished_at': finished_at,
                'error_message': error_message,
            },
            conn=conn,
        )

    async def get_execution_attempt_by_runtime_task_id(
        self,
        runtime_task_id: str,
        *,
        bot_uuid: str,
        connector_id: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionAttempt)
            .join(
                persistence_broadcast.BroadcastExecutionTask,
                persistence_broadcast.BroadcastExecutionTask.id
                == persistence_broadcast.BroadcastExecutionAttempt.execution_task_id,
            )
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionAttempt.runtime_task_id == runtime_task_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def get_execution_task_scope(self, execution_task_id: int, *, conn=None) -> dict[str, Any] | None:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(
                persistence_broadcast.BroadcastExecutionTask.id,
                persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
                persistence_broadcast.BroadcastExecutionTask.action,
                persistence_broadcast.BroadcastExecutionTask.channel,
                persistence_broadcast.BroadcastExecutionTask.status,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id,
                persistence_broadcast.BroadcastExecutionBatch.mode,
                persistence_broadcast.BroadcastExecutionBatch.status.label('batch_status'),
            )
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(persistence_broadcast.BroadcastExecutionTask.id == execution_task_id),
            conn=conn,
        )
        row = result.first()
        if row is None:
            return None
        mapping = getattr(row, '_mapping', None)
        return dict(mapping) if mapping is not None else None

    async def get_execution_batch_unscoped(self, execution_batch_id: int, *, conn=None):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionBatch).where(
                persistence_broadcast.BroadcastExecutionBatch.id == execution_batch_id,
            ),
            conn=conn,
        )
        return self._first_model(result)

    async def claim_next_execution_task(self, conn, *, bot_uuid: str | None = None, connector_id: str | None = None):
        async with self._execution_claim_lock:
            active_result = await self.persistence_mgr.execute_async(
                sqlalchemy.select(sqlalchemy.func.count())
                .select_from(persistence_broadcast.BroadcastExecutionTask)
                .where(persistence_broadcast.BroadcastExecutionTask.status == 'running'),
                conn=conn,
            )
            if int(active_result.scalar() or 0) > 0:
                return None

            result = await self.persistence_mgr.execute_async(
                sqlalchemy.select(
                    persistence_broadcast.BroadcastExecutionTask.id,
                    persistence_broadcast.BroadcastExecutionBatch.bot_uuid,
                    persistence_broadcast.BroadcastExecutionBatch.connector_id,
                )
                .join(
                    persistence_broadcast.BroadcastExecutionBatch,
                    persistence_broadcast.BroadcastExecutionBatch.id
                    == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
                )
                .where(
                    persistence_broadcast.BroadcastExecutionTask.status == 'pending',
                    persistence_broadcast.BroadcastExecutionBatch.mode == 'paste_only',
                    persistence_broadcast.BroadcastExecutionBatch.status.in_(('queued', 'running')),
                    *(
                        (
                            persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                            persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
                        )
                        if bot_uuid and connector_id
                        else ()
                    ),
                )
                .order_by(
                    persistence_broadcast.BroadcastExecutionBatch.created_at.asc(),
                    persistence_broadcast.BroadcastExecutionTask.sequence_no.asc(),
                    persistence_broadcast.BroadcastExecutionTask.id.asc(),
                )
                .limit(1),
                conn=conn,
            )
            row = result.first()
            if row is None:
                return None

            mapping = getattr(row, '_mapping', None)
            if mapping is None:
                return None

            task_id = int(mapping['id'])
            bot_uuid = str(mapping['bot_uuid'])
            connector_id = str(mapping['connector_id'])
            update_result = await self.persistence_mgr.execute_async(
                sqlalchemy.update(persistence_broadcast.BroadcastExecutionTask)
                .where(
                    persistence_broadcast.BroadcastExecutionTask.id == task_id,
                    persistence_broadcast.BroadcastExecutionTask.status == 'pending',
                )
                .values({'status': 'running', 'started_at': sqlalchemy.func.now()}),
                conn=conn,
            )
            if not update_result.rowcount:
                return None

            task = await self.get_execution_task(task_id, bot_uuid=bot_uuid, connector_id=connector_id, conn=conn)
            await self.update_execution_batch(
                int(task.execution_batch_id),
                bot_uuid=bot_uuid,
                connector_id=connector_id,
                updates={'status': 'running', 'started_at': sqlalchemy.func.now(), 'paused_at': None},
                conn=conn,
            )
            return {
                'task': task,
                'scope': {
                    'bot_uuid': bot_uuid,
                    'connector_id': connector_id,
                },
            }

    async def list_execution_tasks_by_status(
        self,
        *,
        bot_uuid: str,
        connector_id: str,
        status: str,
        conn=None,
    ):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastExecutionTask)
            .join(
                persistence_broadcast.BroadcastExecutionBatch,
                persistence_broadcast.BroadcastExecutionBatch.id
                == persistence_broadcast.BroadcastExecutionTask.execution_batch_id,
            )
            .where(
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
                persistence_broadcast.BroadcastExecutionTask.status == status,
            )
            .order_by(
                persistence_broadcast.BroadcastExecutionTask.execution_batch_id.asc(),
                persistence_broadcast.BroadcastExecutionTask.sequence_no.asc(),
                persistence_broadcast.BroadcastExecutionTask.id.asc(),
            ),
            conn=conn,
        )
        return self._all_models(result)

    async def delete_execution_batch(self, execution_batch_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.delete(persistence_broadcast.BroadcastExecutionBatch).where(
                persistence_broadcast.BroadcastExecutionBatch.id == execution_batch_id,
                persistence_broadcast.BroadcastExecutionBatch.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastExecutionBatch.connector_id == connector_id,
            ),
            conn=conn,
        )
        return bool(result.rowcount)

    @staticmethod
    def _first_model(result):
        first = getattr(result, 'first', None)
        row = first() if callable(first) else None
        return BroadcastRepository._coerce_row(row)

    @staticmethod
    def _all_models(result):
        all_rows = getattr(result, 'all', None)
        rows = all_rows() if callable(all_rows) else list(result)
        return [BroadcastRepository._coerce_row(row) for row in rows]

    @staticmethod
    def _coerce_row(row):
        if row is None:
            return None
        if hasattr(row, '__table__'):
            return row
        mapping = getattr(row, '_mapping', None)
        if mapping is not None:
            values = dict(mapping)
            if len(values) == 1:
                first_value = next(iter(values.values()))
                if hasattr(first_value, '__table__'):
                    return first_value
                return first_value
            return row
        if isinstance(row, tuple) and len(row) == 1:
            return row[0]
        return row
