from pathlib import Path
import ast


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


def test_model_provider_seed_is_not_part_of_persistence_core_initialization() -> None:
    source_path = Path(__file__).resolve().parents[3] / 'src' / 'langbot' / 'pkg' / 'persistence' / 'mgr.py'
    module = ast.parse(source_path.read_text(encoding='utf-8'))
    persistence_manager = next(
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == 'PersistenceManager'
    )
    initialize = next(
        node for node in persistence_manager.body if isinstance(node, ast.AsyncFunctionDef) and node.name == 'initialize'
    )

    assert 'write_space_model_providers' not in ast.unparse(initialize)
