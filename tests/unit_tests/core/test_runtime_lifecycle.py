from langbot.pkg.core.lifecycle import RuntimeState, ready_status_code


def test_ready_endpoint_accepts_all_core_usable_states() -> None:
    assert ready_status_code(RuntimeState.CORE_READY) == 200
    assert ready_status_code(RuntimeState.READY) == 200
    assert ready_status_code(RuntimeState.DEGRADED) == 200


def test_ready_endpoint_distinguishes_initializing_and_failed_states() -> None:
    assert ready_status_code(RuntimeState.STARTING) == 503
    assert ready_status_code(RuntimeState.HTTP_READY) == 503
    assert ready_status_code(RuntimeState.CORE_INITIALIZING) == 503
    assert ready_status_code(RuntimeState.FAILED) == 500


async def test_packaged_box_unavailable_transitions_to_degraded_without_shutdown(monkeypatch) -> None:
    from langbot.pkg.core.app import Application
    from langbot.pkg.core.stages.build_app import BuildAppStage

    app = Application()
    app.runtime_state = RuntimeState.CORE_READY
    app.logger = __import__('logging').getLogger('test-runtime-lifecycle')
    stage = BuildAppStage()

    async def fail_optional(_app):
        raise RuntimeError('box unavailable')

    monkeypatch.setattr(stage, '_initialize_remaining', fail_optional)

    await stage._run_packaged_initialization(app)

    assert app.runtime_state is RuntimeState.DEGRADED
    assert app.runtime_failure_code == 'optional-initialization-failed'
    assert not app.shutdown_requested_event.is_set()
