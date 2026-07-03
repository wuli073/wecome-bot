from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from langbot.pkg.persistence.mgr import PersistenceManager


pytestmark = pytest.mark.asyncio


class _EngineHolder:
    def __init__(self, engine) -> None:
        self._engine = engine

    def get_engine(self):
        return self._engine


@pytest.mark.asyncio
async def test_execute_async_uses_passed_connection_without_committing_outer_transaction():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    table = sqlalchemy.Table(
        'sample_records',
        sqlalchemy.MetaData(),
        sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
        sqlalchemy.Column('value', sqlalchemy.String(), nullable=False),
    )

    async with engine.begin() as conn:
        await conn.run_sync(table.create)

    manager = PersistenceManager(SimpleNamespace())
    manager.db = _EngineHolder(engine)

    conn = await engine.connect()
    tx = await conn.begin()
    try:
        await manager.execute_async(
            sqlalchemy.insert(table).values(id=1, value='pending'),
            conn=conn,
        )

        rows_inside_tx = (
            await conn.execute(sqlalchemy.select(table.c.value).where(table.c.id == 1))
        ).all()
        assert rows_inside_tx == [('pending',)]
    finally:
        await tx.rollback()
        await conn.close()

    rows_after_rollback = (
        await manager.execute_async(sqlalchemy.select(table.c.value).where(table.c.id == 1))
    ).all()
    assert rows_after_rollback == []

    await engine.dispose()


@pytest.mark.asyncio
async def test_execute_async_supports_legacy_execute_parameters_without_conn_keyword():
    engine = create_async_engine('sqlite+aiosqlite:///:memory:')
    table = sqlalchemy.Table(
        'sample_records',
        sqlalchemy.MetaData(),
        sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True),
        sqlalchemy.Column('value', sqlalchemy.String(), nullable=False),
    )

    async with engine.begin() as conn:
        await conn.run_sync(table.create)

    manager = PersistenceManager(SimpleNamespace())
    manager.db = _EngineHolder(engine)

    await manager.execute_async(
        sqlalchemy.insert(table).values(id=1, value='committed'),
    )
    row = (
        await manager.execute_async(
            sqlalchemy.select(table.c.value).where(table.c.id == 1),
        )
    ).one()
    assert row == ('committed',)

    await engine.dispose()
