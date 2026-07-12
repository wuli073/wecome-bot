from __future__ import annotations

import asyncio
import contextlib
import os
import re
import typing
from random import randint

import quart
import quart_cors
from werkzeug.exceptions import RequestEntityTooLarge

from ....core import app
from ....utils import importutil
from ....local_connectors import routes as _local_connector_routes  # noqa: F401
from ...mcp.mount import MCPMount
from . import group
from . import groups
from .groups import knowledge as groups_knowledge
from .groups import pipelines as groups_pipelines
from .groups import platform as groups_platform
from .groups import provider as groups_provider
from .groups import resources as groups_resources

importutil.import_modules_in_pkg(groups)
importutil.import_modules_in_pkg(groups_provider)
importutil.import_modules_in_pkg(groups_platform)
importutil.import_modules_in_pkg(groups_pipelines)
importutil.import_modules_in_pkg(groups_knowledge)
importutil.import_modules_in_pkg(groups_resources)


class HTTPController:
    ap: app.Application
    quart_app: quart.Quart

    DEFAULT_HTTP_HOST = '127.0.0.1'
    LOOPBACK_ORIGIN = re.compile(
        r'^http://(?:127\.0\.0\.1|localhost):(?:[1-9]\d{0,3}|[1-5]\d{4}|6[0-4]\d{3}|65[0-4]\d{2}|655[0-2]\d|6553[0-5])$'
    )

    def __init__(self, ap: app.Application) -> None:
        self.ap = ap
        self.quart_app = quart.Quart(__name__)
        quart_cors.cors(
            self.quart_app,
            allow_origin=self.LOOPBACK_ORIGIN,
            allow_headers=['Authorization', 'Content-Type', 'X-API-Key'],
            allow_methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
        )
        self.quart_app.config['MAX_CONTENT_LENGTH'] = group.MAX_FILE_SIZE
        self.mcp_mount: MCPMount | None = None
        self._shutdown_event = asyncio.Event()
        self._listening_event = asyncio.Event()
        self._startup_error: BaseException | None = None

    async def wait_until_listening(self) -> None:
        await self._listening_event.wait()
        if self._startup_error is not None:
            raise self._startup_error

    async def initialize(self) -> None:
        @self.quart_app.errorhandler(RequestEntityTooLarge)
        async def handle_request_entity_too_large(e):
            return quart.jsonify(
                {
                    'code': 400,
                    'msg': 'File size exceeds 10MB limit. Please split large files into smaller parts.',
                }
            ), 400

        await self.register_routes()

        self.mcp_mount = MCPMount(self.ap)
        await self.mcp_mount.start_session_manager()
        self.ap.logger.info('LangBot MCP server mounted at /mcp (API-key authenticated).')

    def run(self) -> typing.Coroutine[typing.Any, typing.Any, None]:
        try:
            host = self._get_bind_host()
            port = int(self.ap.instance_config.data['api']['port'])
            config = self._build_hypercorn_config(host=host, port=port)
            sockets = self._reserve_sockets(config)
            return self._run_with_readiness(
                config=config,
                sockets=sockets,
                shutdown_trigger=self._shutdown_event.wait,
            )
        except Exception as exc:
            self._startup_error = exc
            self._listening_event.set()
            raise

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    async def _run_with_readiness(self, config, sockets, shutdown_trigger) -> None:
        loop = asyncio.get_running_loop()
        ready_future = loop.create_future()

        server_task = loop.create_task(
            self._run_task(
                config=config,
                sockets=sockets,
                shutdown_trigger=shutdown_trigger,
                ready_future=ready_future,
            ),
            name='langbot-http-server',
        )

        def propagate_startup_failure(task: asyncio.Task) -> None:
            if ready_future.done():
                return
            try:
                exception = task.exception()
            except asyncio.CancelledError as exc:
                exception = exc
            if exception is None:
                exception = RuntimeError('HTTP service exited before readiness completed.')
            ready_future.set_exception(exception)

        server_task.add_done_callback(propagate_startup_failure)

        try:
            await ready_future
            await server_task
        except asyncio.CancelledError:
            server_task.cancel()
            await asyncio.gather(server_task, return_exceptions=True)
            self._close_sockets(sockets)
            raise
        except Exception as exc:
            self._startup_error = exc
            self._listening_event.set()
            if not server_task.done():
                server_task.cancel()
                await asyncio.gather(server_task, return_exceptions=True)
            else:
                with contextlib.suppress(Exception):
                    await asyncio.gather(server_task, return_exceptions=True)
            self._close_sockets(sockets)
            raise

    async def _run_task(self, *, config, sockets, shutdown_trigger, ready_future) -> None:
        """Serve the Quart app and resolve readiness only after listen succeeds."""
        import platform

        from asyncio import TaskGroup
        from hypercorn.asyncio.run import Lifespan, TCPServer, UDPServer, WorkerContext, _share_socket
        from hypercorn.utils import ShutdownError, raise_shutdown, repr_socket_addr, wrap_app

        asgi_app = self.quart_app
        if self.mcp_mount is not None:
            asgi_app = self.mcp_mount.wrap(self.quart_app)
        wrapped_app = wrap_app(asgi_app, config.wsgi_max_body_size, None)

        loop = asyncio.get_running_loop()
        lifespan_state: dict = {}
        lifespan = Lifespan(wrapped_app, config, loop, lifespan_state)
        lifespan_task = loop.create_task(lifespan.handle_lifespan())
        await lifespan.wait_for_startup()
        if lifespan_task.done():
            exception = lifespan_task.exception()
            if exception is not None:
                raise exception

        ssl_handshake_timeout = None
        if config.ssl_enabled:
            ssl_context = config.create_ssl_context()
            ssl_handshake_timeout = config.ssl_handshake_timeout

        max_requests = None
        if config.max_requests is not None:
            max_requests = config.max_requests + randint(0, config.max_requests_jitter)
        context = WorkerContext(max_requests)
        server_tasks: set[asyncio.Task] = set()
        servers = []

        async def _server_callback(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            task = asyncio.current_task(loop)
            server_tasks.add(task)
            task.add_done_callback(server_tasks.discard)
            await TCPServer(wrapped_app, loop, config, context, lifespan_state, reader, writer)

        try:
            for sock in sockets.secure_sockets:
                if config.workers > 1 and platform.system() == 'Windows':
                    sock = _share_socket(sock)
                servers.append(
                    await asyncio.start_server(
                        _server_callback,
                        backlog=config.backlog,
                        ssl=ssl_context,
                        sock=sock,
                        ssl_handshake_timeout=ssl_handshake_timeout,
                    )
                )
                bind = repr_socket_addr(sock.family, sock.getsockname())
                await config.log.info(f'Running on https://{bind} (CTRL + C to quit)')
                if not ready_future.done():
                    ready_future.set_result(bind)
                self._listening_event.set()

            for sock in sockets.insecure_sockets:
                if config.workers > 1 and platform.system() == 'Windows':
                    sock = _share_socket(sock)
                servers.append(await asyncio.start_server(_server_callback, backlog=config.backlog, sock=sock))
                bind = repr_socket_addr(sock.family, sock.getsockname())
                await config.log.info(f'Running on http://{bind} (CTRL + C to quit)')
                if not ready_future.done():
                    ready_future.set_result(bind)
                self._listening_event.set()

            for sock in sockets.quic_sockets:
                if config.workers > 1 and platform.system() == 'Windows':
                    sock = _share_socket(sock)
                _, protocol = await loop.create_datagram_endpoint(
                    lambda: UDPServer(wrapped_app, loop, config, context, lifespan_state),
                    sock=sock,
                )
                task = loop.create_task(protocol.run())
                server_tasks.add(task)
                task.add_done_callback(server_tasks.discard)
                bind = repr_socket_addr(sock.family, sock.getsockname())
                await config.log.info(f'Running on https://{bind} (QUIC) (CTRL + C to quit)')
                if not ready_future.done():
                    ready_future.set_result(bind)
                self._listening_event.set()

            if not ready_future.done():
                ready_future.set_result(None)
            self._listening_event.set()

            try:
                async with TaskGroup() as task_group:
                    task_group.create_task(raise_shutdown(shutdown_trigger))
                    task_group.create_task(raise_shutdown(context.terminate.wait))
            except BaseExceptionGroup as error:
                _, other_errors = error.split((ShutdownError, KeyboardInterrupt))
                if other_errors is not None:
                    raise other_errors
            except (ShutdownError, KeyboardInterrupt):
                pass
        finally:
            await context.terminated.set()

            for server in servers:
                server.close()
                await server.wait_closed()

            gathered_server_tasks = asyncio.gather(*server_tasks, return_exceptions=True)
            try:
                await asyncio.wait_for(gathered_server_tasks, config.graceful_timeout)
            except asyncio.TimeoutError:
                pass
            finally:
                await lifespan.wait_for_shutdown()
                lifespan_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await lifespan_task
                self._close_sockets(sockets)

    def _build_hypercorn_config(self, *, host: str, port: int):
        from hypercorn.config import Config as HyperConfig

        config = HyperConfig()
        config.access_log_format = '%(h)s %(r)s %(s)s %(b)s %(D)s'
        config.accesslog = '-'
        config.bind = [f'{host}:{port}']
        config.errorlog = config.accesslog
        return config

    def _reserve_sockets(self, config):
        try:
            return config.create_sockets()
        except OSError as exc:
            bind_target = ', '.join(config.bind)
            message = str(exc)
            if exc.errno in {98, 10048} or getattr(exc, 'winerror', None) in {10013, 10048}:
                raise RuntimeError(f'HTTP port occupied: {bind_target} ({message})') from exc
            raise RuntimeError(f'Failed to bind HTTP service on {bind_target}: {message}') from exc

    def _close_sockets(self, sockets) -> None:
        for sock in (*sockets.secure_sockets, *sockets.insecure_sockets, *sockets.quic_sockets):
            with contextlib.suppress(OSError):
                sock.close()

    def _get_bind_host(self) -> str:
        configured_host = (
            self.ap.instance_config.data.get('api', {}).get('host')
            if self.ap.instance_config is not None
            else None
        )
        if configured_host:
            return str(configured_host)
        return self.DEFAULT_HTTP_HOST

    async def register_routes(self) -> None:
        @self.quart_app.route('/healthz')
        async def healthz():
            return {'code': 0, 'msg': 'ok', 'status': 'ok', 'phase': self.ap.startup_phase}

        @self.quart_app.route('/readyz')
        async def readyz():
            if self.ap.startup_phase == 'ready':
                return {'status': 'ready', 'phase': 'ready'}
            response = {'status': 'initializing', 'phase': self.ap.startup_phase}
            if self.ap.startup_error:
                response['error'] = self.ap.startup_error
                return response, 503
            return response, 503

        for g in group.preregistered_groups:
            ginst = g(self.ap, self.quart_app)
            await ginst.initialize()

        from ....utils import paths

        frontend_path = paths.get_frontend_path()

        @self.quart_app.route('/')
        async def index():
            response = await quart.send_from_directory(frontend_path, 'index.html', mimetype='text/html')
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        @self.quart_app.route('/<path:path>')
        async def static_file(path: str):
            if not (
                os.path.exists(os.path.join(frontend_path, path)) and os.path.isfile(os.path.join(frontend_path, path))
            ):
                if os.path.exists(os.path.join(frontend_path, path + '.html')):
                    path += '.html'
                elif not path.startswith('api/'):
                    if path.startswith('home/'):
                        segments = path.rstrip('/').split('/')
                        for i in range(len(segments) - 1, 0, -1):
                            parent_path = '/'.join(segments[:i]) + '.html'
                            if os.path.exists(os.path.join(frontend_path, parent_path)):
                                response = await quart.send_from_directory(
                                    frontend_path, parent_path, mimetype='text/html'
                                )
                                response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                                response.headers['Pragma'] = 'no-cache'
                                response.headers['Expires'] = '0'
                                return response

                    response = await quart.send_from_directory(frontend_path, 'index.html', mimetype='text/html')
                    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
                    response.headers['Pragma'] = 'no-cache'
                    response.headers['Expires'] = '0'
                    return response
                else:
                    return await quart.send_from_directory(frontend_path, '404.html')

            mimetype = None
            if path.endswith('.html'):
                mimetype = 'text/html'
            elif path.endswith('.js'):
                mimetype = 'application/javascript'
            elif path.endswith('.css'):
                mimetype = 'text/css'
            elif path.endswith('.png'):
                mimetype = 'image/png'
            elif path.endswith('.jpg'):
                mimetype = 'image/jpeg'
            elif path.endswith('.jpeg'):
                mimetype = 'image/jpeg'
            elif path.endswith('.gif'):
                mimetype = 'image/gif'
            elif path.endswith('.svg'):
                mimetype = 'image/svg+xml'
            elif path.endswith('.ico'):
                mimetype = 'image/x-icon'
            elif path.endswith('.json'):
                mimetype = 'application/json'
            elif path.endswith('.txt'):
                mimetype = 'text/plain'

            response = await quart.send_from_directory(frontend_path, path, mimetype=mimetype)
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
