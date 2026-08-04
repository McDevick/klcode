from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel


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

    router = APIRouter(prefix="/api/v1")

    @router.get("/ping")
    def ping():
        return {"status": "pong"}

    @router.get("/sessions")
    def list_sessions():
        return list(sessions.values())

    @router.post("/sessions")
    def create_session(payload: CreateSessionPayload):
        nonlocal next_session_id
        session = {
            "id": f"s{next_session_id}",
            "workspace": payload.workspace,
            "name": payload.name,
            "status": "active",
        }
        next_session_id += 1
        sessions[session["id"]] = session
        return session

    @router.get("/sessions/{session_id}")
    def get_session(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        return session

    @router.patch("/sessions/{session_id}")
    def rename_session(session_id: str, payload: RenameSessionPayload):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        session["name"] = payload.name
        return session

    @router.post("/sessions/{session_id}/close")
    def close_session(session_id: str):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session not found")
        session["status"] = "closed"
        return session

    @router.delete("/sessions/{session_id}")
    def delete_session(session_id: str):
        if sessions.pop(session_id, None) is None:
            raise HTTPException(status_code=404, detail="session not found")
        return Response(status_code=204)

    @router.post("/tasks")
    def create_task(payload: CreateTaskPayload):
        nonlocal next_task_id
        task = {
            "id": f"t{next_task_id}",
            "session_id": payload.session_id,
            "description": payload.description,
            "status": "pending",
        }
        next_task_id += 1
        tasks[task["id"]] = task
        return task

    @router.get("/tasks/{task_id}")
    def get_task(task_id: str):
        task = tasks.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="task not found")
        return task

    @router.post("/config/check")
    def config_check():
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
