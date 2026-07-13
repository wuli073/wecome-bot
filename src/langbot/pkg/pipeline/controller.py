from __future__ import annotations

import asyncio
import traceback

from ..core import app
from ..core import entities as core_entities

import langbot_plugin.api.entities.builtin.pipeline.query as pipeline_query


class Controller:
    """Pipeline query controller."""

    ap: app.Application

    semaphore: asyncio.Semaphore = None
    """Global pipeline concurrency guard."""

    def __init__(self, ap: app.Application):
        self.ap = ap
        self.semaphore = asyncio.Semaphore(self.ap.instance_config.data['concurrency']['pipeline'])

    async def _process_one_query(self, selected_query: pipeline_query.Query) -> pipeline_query.Query:
        async with self.semaphore:
            pipeline_uuid = selected_query.pipeline_uuid

            if pipeline_uuid:
                pipeline = await self.ap.pipeline_mgr.get_pipeline_by_uuid(pipeline_uuid)
                if pipeline:
                    await pipeline.run(selected_query)
                else:
                    self.ap.logger.warning(
                        f'Pipeline {pipeline_uuid} not found for query {selected_query.query_id}, query dropped'
                    )
            else:
                self.ap.logger.warning(
                    f'No pipeline_uuid for query {selected_query.query_id}, query dropped'
                )
        return selected_query

    async def _finish_selected_query(self, selected_query: pipeline_query.Query) -> None:
        async with self.ap.query_pool:
            if hasattr(selected_query, 'variables') and isinstance(selected_query.variables, dict):
                selected_query.variables.pop('_reserved_for_immediate_processing', None)
            (await self.ap.sess_mgr.get_session(selected_query))._semaphore.release()
            self.ap.query_pool.condition.notify_all()

    async def process_query_now(self, selected_query: pipeline_query.Query) -> pipeline_query.Query:
        session = await self.ap.sess_mgr.get_session(selected_query)

        async with self.ap.query_pool:
            if selected_query in self.ap.query_pool.queries:
                self.ap.query_pool.queries.remove(selected_query)
            await session._semaphore.acquire()

        try:
            return await self._process_one_query(selected_query)
        finally:
            await self._finish_selected_query(selected_query)

    async def consumer(self):
        """Consume queued queries in the background."""
        try:
            while True:
                selected_query: pipeline_query.Query | None = None

                async with self.ap.query_pool:
                    queries: list[pipeline_query.Query] = self.ap.query_pool.queries

                    for query in queries:
                        if bool(getattr(query, 'variables', {}).get('_reserved_for_immediate_processing')):
                            continue
                        session = await self.ap.sess_mgr.get_session(query)

                        if not session._semaphore.locked():
                            selected_query = query
                            await session._semaphore.acquire()
                            self.ap.logger.debug(f'Selected query {query.query_id} for processing')
                            break

                    if selected_query is not None:
                        queries.remove(selected_query)
                    else:
                        await self.ap.query_pool.condition.wait()
                        continue

                async def _process_query(query: pipeline_query.Query):
                    try:
                        await self._process_one_query(query)
                    finally:
                        await self._finish_selected_query(query)

                self.ap.task_mgr.create_task(
                    _process_query(selected_query),
                    kind='query',
                    name=f'query-{selected_query.query_id}',
                    scopes=[
                        core_entities.LifecycleControlScope.APPLICATION,
                        core_entities.LifecycleControlScope.PLATFORM,
                    ],
                )

        except Exception as e:
            self.ap.logger.error(f'Controller loop error: {e}')
            self.ap.logger.error(f'Traceback: {traceback.format_exc()}')

    async def run(self):
        """Run the background consumer."""
        await self.consumer()
