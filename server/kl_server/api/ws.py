from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/ws/tasks/{task_id}")
async def task_events(websocket: WebSocket, task_id: str) -> None:
    await websocket.accept()
    try:
        while True:
            payload = await websocket.receive_json()
            await websocket.send_json({"task_id": task_id, **payload})
    except WebSocketDisconnect:
        return
