import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

_connections: dict[str, set[WebSocket]] = {}
_lock = asyncio.Lock()


async def broadcast(task_id: str, payload: dict) -> None:
    async with _lock:
        sockets = set(_connections.get(task_id, ()))
    dead: list[WebSocket] = []
    for websocket in sockets:
        try:
            await websocket.send_json({"task_id": task_id, **payload})
        except Exception:
            dead.append(websocket)
    if dead:
        async with _lock:
            sockets = _connections.setdefault(task_id, set())
            for websocket in dead:
                sockets.discard(websocket)


@router.websocket("/ws/tasks/{task_id}")
async def task_events(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    async with _lock:
        _connections.setdefault(task_id, set()).add(websocket)
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
            await broadcast(task_id, payload)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        async with _lock:
            sockets = _connections.get(task_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    _connections.pop(task_id, None)
