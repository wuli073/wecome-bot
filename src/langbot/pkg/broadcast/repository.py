from __future__ import annotations

from typing import Any

import sqlalchemy

from ..entity.persistence import broadcast as persistence_broadcast


class BroadcastRepository:
    def __init__(self, persistence_mgr) -> None:
        self.persistence_mgr = persistence_mgr

    @staticmethod
    def _scoped_import_batch_ids(import_batch_id: int, *, bot_uuid: str, connector_id: str):
        return sqlalchemy.select(persistence_broadcast.BroadcastImportBatch.id).where(
            persistence_broadcast.BroadcastImportBatch.id == import_batch_id,
            persistence_broadcast.BroadcastImportBatch.bot_uuid == bot_uuid,
            persistence_broadcast.BroadcastImportBatch.connector_id == connector_id,
        )

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

    async def get_variable_profile(self, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastVariableProfile).where(
                persistence_broadcast.BroadcastVariableProfile.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastVariableProfile.connector_id == connector_id,
            )
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

    async def list_group_rules(self, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupRule)
            .where(
                persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            )
            .order_by(
                persistence_broadcast.BroadcastGroupRule.priority.desc(),
                persistence_broadcast.BroadcastGroupRule.id.desc(),
            )
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

    async def list_group_names(self, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupName)
            .where(
                persistence_broadcast.BroadcastGroupName.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupName.connector_id == connector_id,
            )
            .order_by(persistence_broadcast.BroadcastGroupName.name.asc(), persistence_broadcast.BroadcastGroupName.id.asc())
        )
        return self._all_models(result)

    async def create_group_name(self, conn, payload: dict[str, Any]) -> int:
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.insert(persistence_broadcast.BroadcastGroupName).values(payload),
            conn=conn,
        )
        return int(result.inserted_primary_key[0])

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
        result = await self.persistence_mgr.execute_async(stmt)
        return self._all_models(result)

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
        keyword: str | None = None,
    ):
        stmt = sqlalchemy.select(persistence_broadcast.BroadcastDraft).where(
            persistence_broadcast.BroadcastDraft.bot_uuid == bot_uuid,
            persistence_broadcast.BroadcastDraft.connector_id == connector_id,
        )
        if import_batch_id is not None:
            stmt = stmt.where(persistence_broadcast.BroadcastDraft.import_batch_id == import_batch_id)
        if status:
            stmt = stmt.where(persistence_broadcast.BroadcastDraft.status == status)
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
        result = await self.persistence_mgr.execute_async(stmt)
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
