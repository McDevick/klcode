import asyncio
import json
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


def build_ws_router(auth_token: str | None = None, hitl=None) -> APIRouter:
    connections: dict[str, set[WebSocket]] = {}
    lock = asyncio.Lock()
    router = APIRouter()

    async def broadcast(task_id: str, payload: dict) -> None:
        async with lock:
            sockets = set(connections.get(task_id, ()))
        dead: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json({"task_id": task_id, **payload})
            except Exception:
                dead.append(websocket)
        if dead:
            async with lock:
                sockets = connections.setdefault(task_id, set())
                for websocket in dead:
                    sockets.discard(websocket)

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
        async with lock:
            connections.setdefault(task_id, set()).add(websocket)
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
                    if hitl is None:
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
                            state = hitl.approve(action_id)
                        elif decision == "reject":
                            state = hitl.reject(action_id)
                        else:
                            state = hitl.abort(action_id)
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
                    await broadcast(
                        task_id,
                        {
                            "event": "approval_result",
                            "action_id": action_id,
                            "decision": decision,
                            "state": state,
                        },
                    )
                    continue
                await broadcast(task_id, payload)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            async with lock:
                sockets = connections.get(task_id)
                if sockets is not None:
                    sockets.discard(websocket)
                    if not sockets:
                        connections.pop(task_id, None)

    return router
