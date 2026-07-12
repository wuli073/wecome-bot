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
    assert "ap.set_startup_phase('ready')" in source
    assert source.index('await self._initialize_onboarding_core(ap)') < source.index(
        'self._run_packaged_initialization(ap)'
    )
