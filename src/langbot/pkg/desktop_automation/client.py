from __future__ import annotations

from typing import Any, Awaitable, Callable

import aiohttp

from .errors import RUNTIME_PROTOCOL_MISMATCH, RUNTIME_UNAUTHORIZED, RUNTIME_UNAVAILABLE

TransportCallable = Callable[[str, str], Awaitable[tuple[int, dict[str, Any]]]]


class RuntimeErrorBase(RuntimeError):
    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class RuntimeAuthError(RuntimeErrorBase):
    pass


class RuntimeUnavailableError(RuntimeErrorBase):
    pass


class RuntimeProtocolError(RuntimeErrorBase):
    pass


class DesktopRuntimeClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        expected_protocol_version: str = '1',
        transport=None,
        timeout: aiohttp.ClientTimeout | None = None,
    ) -> None:
        self.base_url = base_url.rstrip('/')
        self.token = token
        self.expected_protocol_version = expected_protocol_version
        self.transport = transport
        self.timeout = timeout or aiohttp.ClientTimeout(total=10)

    async def health(self) -> dict[str, Any]:
        payload = await self._request('GET', '/healthz')
        self._assert_protocol(payload)
        return payload

    async def version(self) -> dict[str, Any]:
        return await self.health()

    async def capabilities(self) -> dict[str, Any]:
        return await self._request('GET', '/v1/runtime/status')

    async def ensure_send_backend_ready(self) -> dict[str, Any]:
        return await self.capabilities()

    async def ensure_send_dry_run_backend_ready(self) -> dict[str, Any]:
        return await self.capabilities()

    async def ensure_paste_backend_ready(self) -> dict[str, Any]:
        return await self.capabilities()

    async def create_task(self, *, request: dict[str, Any]) -> dict[str, Any]:
        action = str(request.get('action') or 'paste-draft')
        path = self._task_collection_path(action)
        return await self._request('POST', path, json=request)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request('GET', f'/v1/tasks/{task_id}')

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        return await self._request('POST', f'/v1/tasks/{task_id}/cancel')

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {'Authorization': f'Bearer {self.token}'}
        if self.transport is not None:
            status_code, payload = await self.transport(method, path, headers=headers, json=json)
            return self._coerce_response(status_code, payload)

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.request(method, f'{self.base_url}{path}', headers=headers, json=json) as response:
                    payload = await response.json()
                    return self._coerce_response(response.status, payload)
        except aiohttp.ClientError as exc:
            raise RuntimeUnavailableError('Failed to reach desktop runtime', error_code=RUNTIME_UNAVAILABLE) from exc

    def _coerce_response(self, status_code: int, payload: dict[str, Any]) -> dict[str, Any]:
        if status_code == 401:
            raise RuntimeAuthError(
                payload.get('message', 'Runtime unauthorized'),
                error_code=payload.get('errorCode') or RUNTIME_UNAUTHORIZED,
            )
        if status_code >= 500:
            raise RuntimeUnavailableError(
                payload.get('message', 'Runtime unavailable'),
                error_code=payload.get('errorCode') or RUNTIME_UNAVAILABLE,
            )
        if status_code >= 400:
            raise RuntimeProtocolError(
                payload.get('message', 'Runtime request failed'), error_code=payload.get('errorCode')
            )
        return payload

    def _assert_protocol(self, payload: dict[str, Any]) -> None:
        protocol_version = payload.get('protocolVersion')
        if protocol_version is None:
            return
        if str(protocol_version) != str(self.expected_protocol_version):
            raise RuntimeProtocolError(
                f'Unexpected runtime protocol version: {protocol_version}',
                error_code=RUNTIME_PROTOCOL_MISMATCH,
            )

    @staticmethod
    def _task_collection_path(action: str) -> str:
        normalized = action.replace('_', '-').strip().lower()
        if normalized == 'send-draft':
            return '/v1/tasks/send-draft'
        if normalized == 'diagnose':
            return '/v1/tasks/diagnose'
        if normalized == 'conversation-search':
            return '/v1/tasks/conversation-search'
        if normalized == 'history-search':
            return '/v1/tasks/history-search'
        if normalized == 'quote-reply':
            return '/v1/tasks/quote-reply'
        return '/v1/tasks/paste-draft'


SightFlowRuntimeClient = DesktopRuntimeClient
