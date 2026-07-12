from pathlib import Path


def test_packaged_startup_marks_onboarding_ready_before_optional_services() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / 'src'
        / 'langbot'
        / 'pkg'
        / 'core'
        / 'stages'
        / 'build_app.py'
    ).read_text(encoding='utf-8')

    assert 'async def _initialize_onboarding_core' in source
    assert 'await self._initialize_onboarding_core(ap)' in source
    assert 'ap.set_runtime_state(RuntimeState.CORE_READY)' in source
    assert source.index('await self._initialize_onboarding_core(ap)') < source.index(
        'self._run_packaged_initialization(ap)'
    )


def test_http_listener_does_not_overwrite_packaged_onboarding_readiness() -> None:
    source = (
        Path(__file__).resolve().parents[3]
        / 'src'
        / 'langbot'
        / 'pkg'
        / 'core'
        / 'app.py'
    ).read_text(encoding='utf-8')

    assert 'if self.runtime_state is RuntimeState.STARTING:' in source

    build_source = (
        Path(__file__).resolve().parents[3]
        / 'src'
        / 'langbot'
        / 'pkg'
        / 'core'
        / 'stages'
        / 'build_app.py'
    ).read_text(encoding='utf-8')
    assert 'ap.set_runtime_state(RuntimeState.CORE_READY)' in build_source
