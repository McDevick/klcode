import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from kl_server.api.routes import build_router
from kl_server.api.task_events import ApprovalHub, TaskEventBus, WsForwardingLogger
from kl_server.api.ws import build_ws_router


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
        await _discover_mcp_tools(app.state.deps)
        try:
            yield
        finally:
            await _close_dependencies(runtime_deps if runtime_factory is not None else deps)

    app = FastAPI(lifespan=lifespan)
    app.state.deps = deps
    app.state.auth_token = auth_token
    app.state.event_bus = bus
    app.state.approval_hub = hub
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

    app.include_router(build_router())
    app.include_router(build_ws_router(auth_token, hitl=hitl, bus=bus, hub=hub))
    return app
