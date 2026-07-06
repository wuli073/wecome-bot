from __future__ import annotations

import asyncio
import signal
from types import SimpleNamespace

import pytest

from langbot import __main__ as langbot_main
from langbot.pkg.core import boot


@pytest.mark.asyncio
async def test_signal_before_app_created_sets_pending_shutdown_and_exits_cleanly(monkeypatch):
    captured_handler: dict[int, object] = {}
    observed: dict[str, object] = {}

    def fake_signal(sig, handler):
        captured_handler[sig] = handler

    async def fake_make_app(loop):
        captured_handler[signal.SIGINT](signal.SIGINT, None)
        app = SimpleNamespace()

        def request_shutdown(reason=None):
            observed.setdefault('reason', reason or 'signal')

        async def fake_run():
            return 0

        def dispose():
            observed['disposed'] = True

        app.request_shutdown = request_shutdown
        app.run = fake_run
        app.dispose = dispose
        return app

    monkeypatch.setattr(signal, 'signal', fake_signal)
    monkeypatch.setattr(boot, 'make_app', fake_make_app)

    exit_code = await boot.main(SimpleNamespace(call_soon_threadsafe=lambda fn, *args: fn(*args)))

    assert exit_code == 0
    assert observed['reason'] in {'signal', 'pending-signal'}
    assert observed.get('disposed') is not True


@pytest.mark.asyncio
async def test_boot_main_nonzero_exit_code_is_preserved_by_langbot_main_entry(monkeypatch):
    async def fake_boot_main(loop):
        return 1

    monkeypatch.setattr(langbot_main, 'boot_main', fake_boot_main, raising=False)
    monkeypatch.setattr(langbot_main, 'print_text_safe', lambda *args, **kwargs: None)
    monkeypatch.setattr(langbot_main.argparse.ArgumentParser, 'parse_args', lambda self: SimpleNamespace(
        standalone_runtime=False,
        standalone_box=False,
        debug=False,
    ))

    async def fake_check_deps():
        return []

    async def fake_generate_files():
        return []

    monkeypatch.setattr('langbot.pkg.core.bootutils.deps.check_deps', fake_check_deps)
    monkeypatch.setattr('langbot.pkg.core.bootutils.files.generate_files', fake_generate_files)

    exit_code = await langbot_main.main_entry(asyncio.get_running_loop())

    assert exit_code == 1
