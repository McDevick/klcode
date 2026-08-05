from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from kl_server.models.task import Session, Task


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
        task_id = f"t{next_task_id}"
        task = Task(
            id=task_id,
            session_id=payload.session_id,
            description=payload.description,
        )
        if deps is not None:
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

    @router.post("/config/check")
    def config_check(request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None and getattr(deps, "config_error", None):
            return {
                "status": "degraded",
                "providers": ["mock"],
                "error": deps.config_error,
            }
        return {"status": "ok", "providers": ["mock"]}

    @router.get("/providers")
    def list_providers():
        return [{"name": "mock", "type": "mock"}] + providers

    @router.post("/providers")
    def add_provider(payload: ProviderPayload):
        provider = payload.model_dump()
        providers.append(provider)
        return provider

    @router.get("/models")
    def list_models():
        return [{"name": "mock-model"}]

    @router.get("/keys")
    def list_keys():
        return {"configured": sorted(keys)}

    @router.post("/keys/{ref}")
    def set_key(ref: str, payload: KeyPayload):
        keys.add(ref)
        return {"configured": True}

    @router.get("/keys/{ref}")
    def key_status(ref: str):
        return {"configured": ref in keys}

    @router.delete("/keys/{ref}")
    def clear_key(ref: str):
        keys.discard(ref)
        return {"configured": False}

    return router
