import asyncio
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from kl_server.config.config import AppConfig, ProviderConfig
from kl_server.models.task import Session, Task, TaskStatus
from kl_server.providers.openai_compatible import OpenAICompatibleProvider


def _persist_config(deps) -> None:
    """Write the current AppConfig back to the config YAML file."""
    config_path = getattr(deps, "config_path", None)
    if not config_path:
        return
    Path(config_path).write_text(
        yaml.safe_dump(deps.config.model_dump(), allow_unicode=True),
        encoding="utf-8",
    )


# Task ids of currently executing background tasks, so they can be cancelled.
_running_tasks: dict[str, asyncio.Task] = {}


class CreateSessionPayload(BaseModel):
    workspace: str
    name: str = "default"


class RenameSessionPayload(BaseModel):
    name: str


class CreateTaskPayload(BaseModel):
    session_id: str
    description: str


class ProviderPayload(BaseModel):
    name: str
    type: str
    base_url: str
    default_model: str


class KeyPayload(BaseModel):
    secret: str


class ModelConfigPayload(BaseModel):
    provider: str
    model: str = ""


def _model_available(config: AppConfig) -> list[dict]:
    available = [{"provider": "mock", "model": "mock-model", "base_url": ""}]
    for name, provider_config in config.providers.items():
        available.append(
            {
                "provider": name,
                "model": provider_config.default_model,
                "base_url": provider_config.base_url,
            }
        )
    return available


def _model_state(config: AppConfig) -> dict:
    available = _model_available(config)
    provider = config.default_provider
    model = config.default_model
    if not model:
        if provider == "mock":
            model = "mock-model"
        else:
            provider_config = config.providers.get(provider)
            model = provider_config.default_model if provider_config else ""
    return {"provider": provider, "model": model, "available": available}


def build_router() -> APIRouter:
    sessions: dict[str, dict] = {}
    tasks: dict[str, dict] = {}
    providers: list[dict] = []
    keys: set[str] = set()
    next_session_id = 1
    next_task_id = 1

    def session_dict(session: Session) -> dict:
        return {
            "id": session.id,
            "workspace": session.workspace,
            "name": session.name,
            "status": session.status,
        }

    def task_dict(task: Task) -> dict:
        return {
            "id": task.id,
            "session_id": task.session_id,
            "description": task.description,
            "status": task.status.value,
        }

    def next_seq(existing_ids: list[str], prefix: str) -> int:
        return (
            max(
                (
                    int(item[len(prefix):])
                    for item in existing_ids
                    if item.startswith(prefix) and item[len(prefix):].isdigit()
                ),
                default=0,
            )
            + 1
        )

    router = APIRouter(prefix="/api/v1")

    @router.get("/ping")
    def ping():
        return {"status": "pong"}

    @router.get("/sessions")
    async def list_sessions(request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            return [session_dict(session) for session in await deps.sessions.list()]
        return list(sessions.values())

    @router.post("/sessions")
    async def create_session(payload: CreateSessionPayload, request: Request):
        nonlocal next_session_id
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            # 从已持久化的记录计算下一个序号，避免服务重启后与既有 id 冲突
            existing = await deps.sessions.list()
            next_session_id = next_seq([item.id for item in existing], "s")
        session_id = f"s{next_session_id}"
        session = Session(
            id=session_id,
            workspace=payload.workspace,
            name=payload.name,
        )
        if deps is not None:
            await deps.sessions.create(session)
        next_session_id += 1
        record = session_dict(session)
        if deps is None:
            sessions[session.id] = record
        return record

    @router.get("/sessions/{session_id}")
    async def get_session(session_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                session = await deps.sessions.get(session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            return session_dict(session)
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @router.patch("/sessions/{session_id}")
    async def rename_session(session_id: str, payload: RenameSessionPayload, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                session = await deps.sessions.get(session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            session.name = payload.name
            await deps.sessions.update(session)
            return session_dict(session)
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        session["name"] = payload.name
        return session

    @router.post("/sessions/{session_id}/close")
    async def close_session(session_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                session = await deps.sessions.get(session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            session.status = "closed"
            await deps.sessions.update(session)
            return session_dict(session)
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        session["status"] = "closed"
        return session

    @router.delete("/sessions/{session_id}")
    async def delete_session(session_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                await deps.sessions.delete(session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            return Response(status_code=204)
        if sessions.pop(session_id, None) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return Response(status_code=204)

    @router.post("/tasks")
    async def create_task(payload: CreateTaskPayload, request: Request):
        nonlocal next_task_id
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            existing = await deps.tasks.list()
            next_task_id = next_seq([item.id for item in existing], "t")
        task_id = f"t{next_task_id}"
        task = Task(
            id=task_id,
            session_id=payload.session_id,
            description=payload.description,
        )
        if deps is not None:
            try:
                await deps.sessions.get(payload.session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            await deps.tasks.create(task)
        next_task_id += 1
        record = task_dict(task)
        if deps is None:
            tasks[task.id] = record
        return record

    @router.get("/tasks/{task_id}")
    async def get_task(task_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                task = await deps.tasks.get(task_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="task not found")
            return task_dict(task)
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return task

    @router.post("/tasks/{task_id}/run", status_code=202)
    async def run_task(task_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is None:
            raise HTTPException(
                status_code=501,
                detail="task execution requires a configured server",
            )
        try:
            task = await deps.tasks.get(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        try:
            session = await deps.sessions.get(task.session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found")
        task.status = TaskStatus.RUNNING
        await deps.tasks.update(task)
        loop = deps.loop
        hub = getattr(request.app.state, "approval_hub", None)
        if hub is not None and getattr(loop, "on_approval", None) is None:
            loop.on_approval = lambda tid, info: hub.request(tid, info)
        bus = getattr(request.app.state, "event_bus", None)
        asyncio.create_task(_execute_task(deps, session, task, bus))
        return {"status": "running"}

    @router.post("/tasks/{task_id}/abort")
    async def abort_task(task_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is None:
            raise HTTPException(
                status_code=501,
                detail="task execution requires a configured server",
            )
        try:
            await deps.tasks.get(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        running = _running_tasks.get(task_id)
        if running is not None and not running.done():
            running.cancel()
        await deps.tasks.abort(task_id)
        return {"status": "canceled"}

    @router.post("/tasks/{task_id}/pause")
    async def pause_task(task_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is None:
            raise HTTPException(
                status_code=501,
                detail="task execution requires a configured server",
            )
        try:
            await deps.tasks.pause(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "paused"}

    @router.post("/tasks/{task_id}/continue")
    async def continue_task(task_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is None:
            raise HTTPException(
                status_code=501,
                detail="task execution requires a configured server",
            )
        try:
            await deps.tasks.resume(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"status": "running"}

    @router.post("/config/check")
    def config_check(request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            providers = ["mock"] + list(deps.config.providers.keys())
            if getattr(deps, "config_error", None):
                return {
                    "status": "degraded",
                    "providers": providers,
                    "error": deps.config_error,
                }
            return {"status": "ok", "providers": providers}
        return {"status": "ok", "providers": ["mock"]}

    @router.get("/config/model")
    def get_model_config(request: Request):
        deps = getattr(request.app.state, "deps", None)
        return _model_state(deps.config if deps is not None else AppConfig())

    @router.post("/config/model")
    def set_model_config(payload: ModelConfigPayload, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is None:
            raise HTTPException(status_code=501, detail="requires a configured server")
        if payload.provider != "mock" and payload.provider not in deps.config.providers:
            raise HTTPException(status_code=404, detail="provider not found")
        deps.config.default_provider = payload.provider
        deps.config.default_model = payload.model
        _persist_config(deps)
        return _model_state(deps.config)

    @router.get("/providers")
    def list_providers(request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            listed = [{"name": "mock", "type": "mock"}]
            listed.extend(
                {
                    "name": name,
                    "type": provider_config.type,
                    "base_url": provider_config.base_url,
                    "default_model": provider_config.default_model,
                }
                for name, provider_config in deps.config.providers.items()
            )
            return listed
        return [{"name": "mock", "type": "mock"}] + providers

    @router.post("/providers")
    async def add_provider(payload: ProviderPayload, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            provider_config = ProviderConfig(
                name=payload.name,
                type=payload.type,
                base_url=payload.base_url,
                default_model=payload.default_model,
            )
            deps.config.providers[payload.name] = provider_config
            _persist_config(deps)
            deps.provider_registry.register(
                payload.name,
                OpenAICompatibleProvider(
                    base_url=payload.base_url,
                    api_key=deps.credentials.get(payload.name),
                    model=payload.default_model,
                ),
            )
            return payload
        provider = payload.model_dump()
        providers.append(provider)
        return provider

    @router.get("/models")
    def list_models(request: Request):
        deps = getattr(request.app.state, "deps", None)
        return _model_available(deps.config if deps is not None else AppConfig())

    @router.get("/keys")
    def list_keys(request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            return {"configured": sorted(deps.credentials.safe_snapshot())}
        return {"configured": sorted(keys)}

    @router.post("/keys/{ref}")
    def set_key(ref: str, payload: KeyPayload, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            deps.credentials.set(ref, payload.secret)
            return {"configured": True}
        keys.add(ref)
        return {"configured": True}

    @router.get("/keys/{ref}")
    def key_status(ref: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            return {"configured": deps.credentials.has(ref)}
        return {"configured": ref in keys}

    @router.delete("/keys/{ref}")
    def clear_key(ref: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            deps.credentials.clear(ref)
            return {"configured": False}
        keys.discard(ref)
        return {"configured": False}

    return router


async def _execute_task(deps, session, task, bus) -> None:
    """Run a task through the composed agent loop and publish the outcome.

    Runs in the background (spawned by ``run_task``); lifecycle events are
    streamed to the event bus by the loop's forwarded logger.
    """
    _running_tasks[task.id] = asyncio.current_task()
    try:
        result = await deps.loop.run(session, task.description, task_id=task.id)
    except Exception as exc:
        task.status = TaskStatus.FAILED
        await deps.tasks.update(task)
        if bus is not None:
            await bus.broadcast(
                task.id,
                {"event": "task_end", "status": "failed", "error": str(exc)[:500]},
            )
        return
    finally:
        _running_tasks.pop(task.id, None)
    task.status = TaskStatus.SUCCEEDED if result == "DONE" else TaskStatus.FAILED
    await deps.tasks.update(task)
    if bus is not None:
        await bus.broadcast(
            task.id,
            {"event": "task_end", "status": task.status.value, "result": result},
        )
