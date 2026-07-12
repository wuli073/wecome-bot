from __future__ import annotations

from enum import StrEnum


class RuntimeState(StrEnum):
    STARTING = 'STARTING'
    HTTP_READY = 'HTTP_READY'
    CORE_INITIALIZING = 'CORE_INITIALIZING'
    CORE_READY = 'CORE_READY'
    READY = 'READY'
    DEGRADED = 'DEGRADED'
    FAILED = 'FAILED'
    STOPPING = 'STOPPING'
    STOPPED = 'STOPPED'


CORE_USABLE_STATES = frozenset({RuntimeState.CORE_READY, RuntimeState.READY, RuntimeState.DEGRADED})
INITIALIZING_STATES = frozenset(
    {RuntimeState.STARTING, RuntimeState.HTTP_READY, RuntimeState.CORE_INITIALIZING, RuntimeState.STOPPING}
)


def ready_status_code(state: RuntimeState) -> int:
    if state in CORE_USABLE_STATES:
        return 200
    if state is RuntimeState.FAILED:
        return 500
    return 503


def runtime_payload(
    state: RuntimeState,
    *,
    session_id: str = '',
    build_id: str = '',
    failure_code: str | None = None,
) -> dict[str, object]:
    return {
        'state': state.value,
        'phase': state.value,
        'coreReady': state in CORE_USABLE_STATES,
        'ready': state is RuntimeState.READY,
        'degraded': state is RuntimeState.DEGRADED,
        'failureCode': failure_code,
        'sessionId': session_id,
        'buildId': build_id,
    }
