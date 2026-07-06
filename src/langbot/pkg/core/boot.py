from __future__ import annotations

import traceback
import asyncio
import os

from . import app
from . import stage
from ..utils import constants, importutil

# Import startup stage implementation to register
from . import stages

importutil.import_modules_in_pkg(stages)


stage_order = [
    'LoadConfigStage',
    'GenKeysStage',
    'SetupLoggerStage',
    'BuildAppStage',
    'ShowNotesStage',
]


async def make_app(loop: asyncio.AbstractEventLoop) -> app.Application:
    # Determine if it is debug mode
    if 'DEBUG' in os.environ and os.environ['DEBUG'] in ['true', '1']:
        constants.debug_mode = True

    ap = app.Application()

    ap.event_loop = loop

    # Execute startup stage
    for stage_name in stage_order:
        stage_cls = stage.preregistered_stages[stage_name]
        stage_inst = stage_cls()

        await stage_inst.run(ap)

    await ap.initialize()

    return ap


async def main(loop: asyncio.AbstractEventLoop) -> int:
    app_inst: app.Application | None = None
    pending_shutdown = False
    try:
        # Hang system signal processing
        import signal

        def signal_handler(sig, frame):
            nonlocal pending_shutdown
            pending_shutdown = True
            if app_inst is not None:
                loop.call_soon_threadsafe(app_inst.request_shutdown, f'signal:{sig}')

        signal.signal(signal.SIGINT, signal_handler)

        app_inst = await make_app(loop)
        if pending_shutdown:
            app_inst.request_shutdown('pending-signal')
        return await app_inst.run()
    except Exception:
        if app_inst is not None:
            await app_inst.shutdown()
            app_inst.dispose()
        traceback.print_exc()
        return 1
