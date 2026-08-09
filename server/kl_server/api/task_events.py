"""Task event bus and approval hub bridging task execution to WebSocket clients."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


class TaskEventBus:
    """Fan-out task events to subscribed WebSocket connections."""

    def __init__(self) -> None:
        self._connections: dict[str, set[Any]] = {}
        self._lock = asyncio.Lock()

    async def register(self, task_id: str, websocket: Any) -> None:
        async with self._lock:
            self._connections.setdefault(task_id, set()).add(websocket)

    async def unregister(self, task_id: str, websocket: Any) -> None:
        async with self._lock:
            sockets = self._connections.get(task_id)
            if sockets is None:
                return
            sockets.discard(websocket)
            if not sockets:
                self._connections.pop(task_id, None)

    async def connection_count(self) -> int:
        async with self._lock:
            return sum(len(sockets) for sockets in self._connections.values())

    async def broadcast(self, task_id: str, payload: dict) -> None:
        async with self._lock:
            sockets = set(self._connections.get(task_id, ()))
        dead: list[Any] = []
        for websocket in sockets:
            try:
                await websocket.send_json({"task_id": task_id, **payload})
            except Exception:
                dead.append(websocket)
        if dead:
            async with self._lock:
                sockets = self._connections.setdefault(task_id, set())
                for websocket in dead:
                    sockets.discard(websocket)

    def emit_sync(self, task_id: str, payload: dict) -> None:
        """Fire-and-forget broadcast from synchronous code (e.g. a logger).

        Safe only when called inside a running event loop.
        """
        loop = asyncio.get_running_loop()
        loop.create_task(self.broadcast(task_id, payload))


class WsForwardingLogger:
    """Wrap an EventLogger and forward every write to the event bus.

    The agent loop writes lifecycle events through its ``logger``; wrapping it
    lets task execution stream those events to WebSocket subscribers.
    """

    def __init__(self, inner, bus: TaskEventBus) -> None:
        self._inner = inner
        self._bus = bus

    def write(self, event: str, payload: dict, task_id: str = "") -> None:
        self._inner.write(event, payload, task_id)
        # 审批事件由 ApprovalHub/WS 路由统一广播顶层字段，避免 logger 与 hub
        # 双通道发同一事件时 TUI 被嵌套 payload 覆盖。
        if event in {"approval_request", "approval_complete", "approval_result"}:
            return
        self._bus.emit_sync(task_id, {"event": event, "payload": payload})


class ApprovalHub:
    """Coordinates HITL approval requests with waiting decision futures.

    A task run publishes an approval request over the event bus, then awaits a
    decision that WebSocket clients resolve via ``resolve()``. Unanswered
    requests time out and default to ``reject``.
    """

    def __init__(self, bus: TaskEventBus, timeout: float = 300.0) -> None:
        self.bus = bus
        self.timeout = timeout
        self._waiters: dict[str, asyncio.Future] = {}

    async def request(self, task_id: str, info: dict) -> str:
        action_id = info["action_id"]
        # 先注册 waiter 再广播：客户端可能在收到 approval_request 事件后立刻
        # resolve，若 resolve 先于 _waiters 注册则决策会丢失并等满超时。
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._waiters[action_id] = future
        await self.bus.broadcast(
            task_id,
            {
                "event": "approval_request",
                "action_id": action_id,
                "tool": info.get("tool", ""),
                "args": info.get("args", {}),
                "level": info.get("level", ""),
                "timeout_seconds": self.timeout,
            },
        )
        try:
            return await asyncio.wait_for(future, self.timeout)
        except asyncio.TimeoutError:
            logger.warning("approval request %s timed out; rejecting", action_id)
            await self.bus.broadcast(
                task_id,
                {
                    "event": "approval_complete",
                    "action_id": action_id,
                    "decision": "timeout",
                },
            )
            return "timeout"
        finally:
            self._waiters.pop(action_id, None)

    def resolve(self, action_id: str, decision: str) -> None:
        future = self._waiters.get(action_id)
        if future is not None and not future.done():
            future.set_result(decision)
