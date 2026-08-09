import asyncio
import logging
import os
import secrets
import signal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from kl_server.api.routes import build_router
from kl_server.api.task_events import ApprovalHub, TaskEventBus, WsForwardingLogger
from kl_server.api.ws import build_ws_router
from kl_server.models.task import TaskStatus
from kl_server.storage.database import DatabaseCorruptionError


logger = logging.getLogger(__name__)


async def _close_dependencies(deps) -> None:
    if deps is None:
        return
    for name in ("db", "memory", "mcp"):
        resource = getattr(deps, name, None)
        close = getattr(resource, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:
                pass


async def _active_task_count(deps) -> int:
    if deps is None:
        return 0
    tasks = await deps.tasks.list()
    active = {TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL, TaskStatus.PAUSED}
    return sum(1 for task in tasks if task.status in active)


def _default_idle_exit() -> None:
    try:
        os.kill(os.getpid(), signal.SIGTERM)
    except Exception:
        os._exit(0)


async def _idle_reaper(app: FastAPI, timeout: float) -> None:
    if timeout <= 0:
        return
    idle_since: float | None = None
    while True:
        await asyncio.sleep(min(1.0, timeout / 2))
        deps = getattr(app.state, "deps", None)
        bus = getattr(app.state, "event_bus", None)
        if deps is None or bus is None:
            continue
        try:
            active_tasks = await _active_task_count(deps)
            connections = await bus.connection_count()
        except Exception:
            continue
        if active_tasks or connections:
            idle_since = None
            continue
        now = asyncio.get_running_loop().time()
        if idle_since is None:
            idle_since = now
            continue
        if now - idle_since >= timeout:
            logger.info("auto daemon idle; shutting down")
            exit_callback = getattr(app.state, "idle_exit", _default_idle_exit)
            exit_callback()
            return


async def _discover_mcp_tools(deps) -> None:
    if deps is None:
        return
    mcp = getattr(deps, "mcp", None)
    tool_registry = getattr(deps, "tool_registry", None)
    if mcp is None or tool_registry is None:
        return
    from kl_server.extensions import register_mcp_tools

    try:
        registered = await register_mcp_tools(tool_registry, mcp)
        if registered:
            logger.info("Registered %d MCP tools", len(registered))
    except Exception:
        logger.exception("Failed to register MCP tools")


async def _recover_stale_tasks(deps) -> int:
    tasks = getattr(deps, "tasks", None)
    if tasks is None or not hasattr(tasks, "recover_stale_tasks"):
        return 0
    return await tasks.recover_stale_tasks()


def _wire_runtime_events(deps, bus: TaskEventBus) -> None:
    """Forward the composed agent loop's lifecycle events to the event bus."""
    if deps is None:
        return
    loop = getattr(deps, "loop", None)
    logger = getattr(deps, "logger", None)
    if loop is not None and logger is not None and getattr(loop, "logger", None) is logger:
        loop.logger = WsForwardingLogger(logger, bus)


def create_app(
    auth_token: str | None = None,
    hitl=None,
    deps=None,
    runtime_factory=None,
    bus: TaskEventBus | None = None,
    hub: ApprovalHub | None = None,
    daemon_source: str = "manual",
    idle_timeout: float | None = None,
) -> FastAPI:
    bus = bus or TaskEventBus()
    hub = hub or ApprovalHub(bus=bus)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if runtime_factory is not None:
            runtime_deps, runtime_token = runtime_factory()
            app.state.deps = runtime_deps
            app.state.auth_token = runtime_token
            _wire_runtime_events(runtime_deps, bus)
            recovered = await _recover_stale_tasks(runtime_deps)
            if recovered:
                logger.info("Marked %d stale tasks failed after daemon restart", recovered)
            config = getattr(runtime_deps, "config", None)
            guardrail = getattr(config, "guardrail", None) if config is not None else None
            if guardrail is not None:
                hub.timeout = guardrail.approval_timeout_seconds
        await _discover_mcp_tools(app.state.deps)
        idle_task: asyncio.Task | None = None
        if app.state.daemon_source == "auto" and app.state.idle_timeout is not None:
            idle_task = asyncio.create_task(
                _idle_reaper(app, app.state.idle_timeout)
            )
        try:
            yield
        finally:
            if idle_task is not None:
                idle_task.cancel()
                try:
                    await idle_task
                except (asyncio.CancelledError, Exception):
                    pass
            await _close_dependencies(runtime_deps if runtime_factory is not None else deps)

    app = FastAPI(lifespan=lifespan)
    app.state.deps = deps
    app.state.auth_token = auth_token
    app.state.event_bus = bus
    app.state.approval_hub = hub
    app.state.daemon_source = daemon_source
    app.state.idle_timeout = idle_timeout
    app.state.idle_exit = _default_idle_exit
    if deps is not None:
        config = getattr(deps, "config", None)
        guardrail = getattr(config, "guardrail", None) if config is not None else None
        if guardrail is not None:
            hub.timeout = guardrail.approval_timeout_seconds
    _wire_runtime_events(deps, bus)

    @app.middleware("http")
    async def auth_middleware(request, call_next):
        token = getattr(app.state, "auth_token", None)
        if token and request.url.path != "/health":
            header = request.headers.get("Authorization", "")
            if not secrets.compare_digest(header, f"Bearer {token}"):
                return JSONResponse(status_code=401, content={"detail": "unauthorized"})
        return await call_next(request)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/daemon/status")
    async def daemon_status(request: Request):
        state = request.app.state
        deps = getattr(state, "deps", None)
        if deps is None:
            return {
                "source": state.daemon_source,
                "running_tasks": 0,
                "ws_connections": 0,
            }
        return {
            "source": state.daemon_source,
            "running_tasks": await _active_task_count(deps),
            "ws_connections": await state.event_bus.connection_count(),
        }

    @app.exception_handler(DatabaseCorruptionError)
    async def database_corruption_handler(request, exc: DatabaseCorruptionError):
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    app.include_router(build_router())
    app.include_router(build_ws_router(auth_token, hitl=hitl, bus=bus, hub=hub))
    return app
