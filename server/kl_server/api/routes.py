import asyncio
import json
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from kl_server.config.config import AppConfig, ProviderConfig
from kl_server.core.guardrail import normalize_workspace_mode
from kl_server.core.snapshot import SnapshotManager
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
    name: str | None = None


class RenameSessionPayload(BaseModel):
    name: str = ""
    rules: str | None = None  # None = 不修改；空串 = 清空


class CreateTaskPayload(BaseModel):
    session_id: str
    description: str
    workspace_mode: str = "git"
    branch: str | None = None

    @field_validator("workspace_mode")
    @classmethod
    def _valid_workspace_mode(cls, value: str) -> str:
        if value not in {"git", "managed", "unmanaged", "snapshot", "manual"}:
            raise ValueError(f"unknown workspace mode: {value}")
        return value


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


def _history_message(record: dict) -> dict | None:
    event = record.get("event")
    payload = record.get("payload") or {}
    if event == "loop_start":
        task = payload.get("task")
        if task:
            return {"type": "user", "content": task}
        return None
    if event == "agent_message":
        text = payload.get("text")
        if text:
            return {"type": "agent", "content": text, "kind": "text"}
        return None
    if event == "llm_result":
        if payload.get("tool_calls"):
            return None
        text = str(payload.get("text") or "").strip()
        if text == "DONE":
            return None
        if text.startswith("DONE: "):
            text = text[len("DONE: ") :]
        if text:
            return {"type": "agent", "content": text, "kind": "text"}
        return None
    if event == "tool_result":
        return {
            "type": "tool",
            "name": payload.get("tool", ""),
            "args": payload.get("args"),
            "ok": bool(payload.get("ok")),
            "error": payload.get("error"),
            "output": payload.get("output"),
        }
    if event == "provider_error":
        return {
            "type": "agent",
            "content": f"错误: {payload.get('error', 'unknown')}",
            "kind": "error",
        }
    return None


async def _load_session_history(deps, session_id: str) -> list[dict]:
    tasks = [task for task in await deps.tasks.list() if task.session_id == session_id]
    task_ids = {task.id for task in tasks}
    log_path = getattr(deps.logger, "path", None)
    if not log_path or not Path(log_path).exists():
        return []

    records: list[dict] = []
    for line in Path(log_path).read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("task_id") in task_ids:
            records.append(record)
    records.sort(key=lambda record: record.get("timestamp", ""))

    messages: list[dict] = []
    for record in records:
        message = _history_message(record)
        if message is not None:
            messages.append(message)
    return messages


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
            "provider": session.provider,
            "model": session.model,
            "rules": session.rules,
        }

    def task_dict(task: Task) -> dict:
        return {
            "id": task.id,
            "session_id": task.session_id,
            "description": task.description,
            "status": task.status.value,
            "workspace_mode": task.workspace_mode,
            "branch": task.branch,
            "snapshot_path": task.snapshot_path,
            "summary": task.summary or "",
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
            result = []
            for session in await deps.sessions.list():
                record = session_dict(session)
                record["task_count"] = await deps.tasks.count_by_session(session.id)
                result.append(record)
            return result
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
            name=payload.name or session_id,
            provider=deps.config.default_provider if deps is not None else "mock",
            model=deps.config.default_model if deps is not None else "mock-model",
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

    @router.get("/sessions/{session_id}/history")
    async def get_session_history(session_id: str, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                await deps.sessions.get(session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            return await _load_session_history(deps, session_id)
        if session_id not in sessions:
            raise HTTPException(status_code=404, detail="session not found")
        return []

    @router.patch("/sessions/{session_id}")
    async def rename_session(session_id: str, payload: RenameSessionPayload, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            try:
                session = await deps.sessions.get(session_id)
            except KeyError:
                raise HTTPException(status_code=404, detail="session not found")
            if payload.name:
                session.name = payload.name
            if payload.rules is not None:
                session.rules = payload.rules
            await deps.sessions.update(session)
            return session_dict(session)
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        if payload.name:
            session["name"] = payload.name
        if payload.rules is not None:
            session["rules"] = payload.rules
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
            workspace_mode=payload.workspace_mode,
            branch=payload.branch,
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
        if task.status in (TaskStatus.RUNNING, TaskStatus.AWAITING_APPROVAL):
            raise HTTPException(
                status_code=409,
                detail=f"task already {task.status.value}",
            )
        try:
            session = await deps.sessions.get(task.session_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="session not found")
        loop = deps.loop
        # 重新 run 前清除可能残留的暂停门控（例如暂停后被 abort 的任务）。
        loop.set_paused(task.id, False)
        task.status = TaskStatus.RUNNING
        await deps.tasks.update(task)
        hub = getattr(request.app.state, "approval_hub", None)
        if hub is not None and getattr(loop, "on_approval", None) is None:
            loop.on_approval = lambda tid, info: hub.request(tid, info)
        bus = getattr(request.app.state, "event_bus", None)
        # 先取得句柄再返回响应，保证紧随其后的 abort 一定能 cancel 到后台任务
        # （否则 abort 可能落在协程尚未把自身写入 _running_tasks 的窗口里）。
        _running_tasks[task.id] = asyncio.create_task(_execute_task(deps, session, task, bus))
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
            task = await deps.tasks.get(task_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="task not found")
        if task.status in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED):
            raise HTTPException(
                status_code=409,
                detail=f"cannot abort task in {task.status.value}",
            )
        running = _running_tasks.pop(task_id, None)
        if running is not None and not running.done():
            running.cancel()
        await deps.tasks.abort(task_id)
        bus = getattr(request.app.state, "event_bus", None)
        if bus is not None:
            await bus.broadcast(
                task_id,
                {"event": "task_end", "status": TaskStatus.CANCELED.value},
            )
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
        deps.loop.set_paused(task_id, True)
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
        deps.loop.set_paused(task_id, False)
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
        if payload.provider != "mock":
            if payload.provider not in deps.config.providers:
                raise HTTPException(status_code=404, detail="provider not found")
            try:
                deps.provider_registry.get(payload.provider)
            except KeyError:
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
            # 刷新已注册 provider 的 api_key：provider 注册时取的 key 可能为空
            # （bootstrap 只从环境变量取），key set 后必须即时生效。
            try:
                provider = deps.provider_registry.get(ref)
            except KeyError:
                provider = None
            if provider is not None and hasattr(provider, "api_key"):
                provider.api_key = payload.secret
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
    try:
        # unmanaged 工作区没有 git 兜底，运行前做一次快照并记录路径；
        # 快照只保留不自动回滚，失败也不阻断任务执行。
        if normalize_workspace_mode(task.workspace_mode) == "unmanaged":
            manager = SnapshotManager(session.workspace)
            try:
                snapshot = await asyncio.to_thread(manager.create)
                task.snapshot_path = str(snapshot)
                await deps.tasks.update(task)
            except Exception:
                task.snapshot_path = None
        result = await deps.loop.run(
            session,
            task.description,
            task_id=task.id,
            workspace_mode=task.workspace_mode,
        )
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
    if result in ("NEEDS_APPROVAL", "ABORTED", "MAX_ITERATIONS"):
        if result == "NEEDS_APPROVAL":
            task.status = TaskStatus.AWAITING_APPROVAL
        elif result == "ABORTED":
            task.status = TaskStatus.CANCELED
        else:
            task.status = TaskStatus.FAILED
            task.summary = "max_iterations reached"
    else:
        # 原生 tool calling：无工具调用时的回复即最终回答
        task.status = TaskStatus.SUCCEEDED
        task.summary = result[len("DONE: ") :] if result.startswith("DONE: ") else result
    await deps.tasks.update(task)
    if bus is not None:
        await bus.broadcast(
            task.id,
            {"event": "task_end", "status": task.status.value, "result": result},
        )
