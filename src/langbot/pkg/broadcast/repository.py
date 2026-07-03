from __future__ import annotations

from typing import Any

import sqlalchemy

from ..entity.persistence import broadcast as persistence_broadcast


class BroadcastRepository:
    def __init__(self, persistence_mgr) -> None:
        self.persistence_mgr = persistence_mgr

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

    async def get_template(self, template_id: int, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastTemplate).where(
                persistence_broadcast.BroadcastTemplate.id == template_id,
                persistence_broadcast.BroadcastTemplate.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastTemplate.connector_id == connector_id,
            )
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
        return await self.get_template(template_id, bot_uuid=bot_uuid, connector_id=connector_id)

    async def delete_template(self, template_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
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

    async def get_group_rule(self, rule_id: int, *, bot_uuid: str, connector_id: str):
        result = await self.persistence_mgr.execute_async(
            sqlalchemy.select(persistence_broadcast.BroadcastGroupRule).where(
                persistence_broadcast.BroadcastGroupRule.id == rule_id,
                persistence_broadcast.BroadcastGroupRule.bot_uuid == bot_uuid,
                persistence_broadcast.BroadcastGroupRule.connector_id == connector_id,
            )
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
        return await self.get_group_rule(rule_id, bot_uuid=bot_uuid, connector_id=connector_id)

    async def delete_group_rule(self, rule_id: int, *, bot_uuid: str, connector_id: str, conn=None) -> bool:
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
