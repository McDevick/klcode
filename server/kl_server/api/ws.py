import json
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from kl_server.api.task_events import ApprovalHub, TaskEventBus


def _effective_hitl(websocket: WebSocket, hitl) -> object | None:
    if hitl is not None:
        return hitl
    deps = getattr(websocket.app.state, "deps", None)
    if deps is not None:
        executor = getattr(deps, "executor", None)
        guardrail = getattr(executor, "guardrail", None) if executor is not None else None
        return getattr(guardrail, "hitl", None)
    return None


def build_ws_router(
    auth_token: str | None = None,
    hitl=None,
    bus: TaskEventBus | None = None,
    hub: ApprovalHub | None = None,
) -> APIRouter:
    bus = bus or TaskEventBus()
    router = APIRouter()

    @router.websocket("/ws/daemon")
    async def daemon_presence(websocket: WebSocket) -> None:
        effective_token = (
            auth_token
            if auth_token is not None
            else getattr(websocket.app.state, "auth_token", None)
        )
        if effective_token is not None:
            auth = websocket.headers.get("Authorization", "")
            expected = f"Bearer {effective_token}"
            query_token = websocket.query_params.get("token")
            valid_header = secrets.compare_digest(auth, expected)
            valid_query = query_token is not None and secrets.compare_digest(query_token, effective_token)
            if not valid_header and not valid_query:
                await websocket.close(code=1008)
                return
        await websocket.accept()
        await bus.register("_daemon", websocket)
        try:
            while True:
                await websocket.receive_text()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await bus.unregister("_daemon", websocket)

    @router.websocket("/ws/tasks/{task_id}")
    async def task_events(websocket: WebSocket, task_id: str) -> None:
        effective_token = (
            auth_token
            if auth_token is not None
            else getattr(websocket.app.state, "auth_token", None)
        )
        if effective_token is not None:
            auth = websocket.headers.get("Authorization", "")
            expected = f"Bearer {effective_token}"
            query_token = websocket.query_params.get("token")
            valid_header = secrets.compare_digest(auth, expected)
            valid_query = query_token is not None and secrets.compare_digest(query_token, effective_token)
            if not valid_header and not valid_query:
                await websocket.close(code=1008)
                return
        await websocket.accept()
        await bus.register(task_id, websocket)
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send_json({"task_id": task_id, "error": "invalid json"})
                    continue
                if not isinstance(payload, dict):
                    await websocket.send_json({"task_id": task_id, "error": "payload must be object"})
                    continue
                payload.pop("task_id", None)
                decision = payload.get("event")
                if decision in {"approve", "reject", "abort"}:
                    action_id = payload.get("action_id")
                    if not isinstance(action_id, str) or not action_id:
                        await websocket.send_json(
                            {"task_id": task_id, "error": "action_id is required", "event": decision}
                        )
                        continue
                    effective_hitl = _effective_hitl(websocket, hitl)
                    if effective_hitl is None:
                        await websocket.send_json(
                            {
                                "task_id": task_id,
                                "error": "hitl is not configured",
                                "event": decision,
                                "action_id": action_id,
                            }
                        )
                        continue
                    try:
                        if decision == "approve":
                            state = effective_hitl.approve(action_id)
                        elif decision == "reject":
                            state = effective_hitl.reject(action_id)
                        else:
                            state = effective_hitl.abort(action_id)
                    except ValueError as exc:
                        await websocket.send_json(
                            {
                                "task_id": task_id,
                                "error": str(exc),
                                "event": decision,
                                "action_id": action_id,
                            }
                        )
                        continue
                    if hub is not None:
                        hub.resolve(action_id, decision)
                    await bus.broadcast(
                        task_id,
                        {
                            "event": "approval_result",
                            "action_id": action_id,
                            "decision": decision,
                            "state": state,
                        },
                    )
                    continue
                await bus.broadcast(task_id, payload)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await bus.unregister(task_id, websocket)

    return router
