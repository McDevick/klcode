"""Tests for the task event bus and approval hub used by the TUI/WS bridge."""

import asyncio

import pytest

from kl_server.api.task_events import ApprovalHub, TaskEventBus


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []
        self.fail_next = False

    async def send_json(self, payload: dict) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("socket closed")
        self.sent.append(payload)


class FakeBus:
    def __init__(self):
        self.broadcasted: list[tuple[str, dict]] = []

    async def broadcast(self, task_id: str, payload: dict) -> None:
        self.broadcasted.append((task_id, payload))


@pytest.mark.asyncio
async def test_bus_broadcast_delivers_to_subscribers_and_drops_dead():
    bus = TaskEventBus()
    alive = FakeWebSocket()
    dead = FakeWebSocket()
    dead.fail_next = True
    await bus.register("t1", alive)
    await bus.register("t1", dead)

    await bus.broadcast("t1", {"event": "loop_start"})

    assert len(alive.sent) == 1
    assert alive.sent[0]["task_id"] == "t1"
    assert alive.sent[0]["event"] == "loop_start"
    assert alive.sent[0]["event_id"] == "t1:1"
    assert dead.sent == []
    # dead connection removed from the set; next broadcast only reaches alive
    await bus.broadcast("t1", {"event": "second"})
    assert len(alive.sent) == 2

    await bus.unregister("t1", alive)
    await bus.broadcast("t1", {"event": "third"})
    assert len(alive.sent) == 2


@pytest.mark.asyncio
async def test_bus_replays_recent_events():
    bus = TaskEventBus()
    first = FakeWebSocket()
    await bus.register("t1", first)
    await bus.broadcast("t1", {"event": "loop_start"})
    await bus.broadcast("t1", {"event": "tool_result"})

    second = FakeWebSocket()
    await bus.replay("t1", second)

    assert [item["event"] for item in second.sent] == ["loop_start", "tool_result"]
    assert [item["event_id"] for item in second.sent] == ["t1:1", "t1:2"]

@pytest.mark.asyncio
async def test_bus_unregister_removes_empty_task_key():
    bus = TaskEventBus()
    socket = FakeWebSocket()
    await bus.register("t1", socket)
    await bus.unregister("t1", socket)
    assert "t1" not in bus._connections


@pytest.mark.asyncio
async def test_hub_request_broadcasts_approval_and_waits_for_resolution():
    bus = FakeBus()
    hub = ApprovalHub(bus=bus, timeout=5.0)

    async def resolver():
        await asyncio.sleep(0.01)
        hub.resolve("a1", "approve")

    request_task = asyncio.create_task(
        hub.request("t1", {"action_id": "a1", "tool": "run_command", "args": {"command": "rm -rf /"}, "level": "critical"})
    )
    await asyncio.sleep(0.01)
    resolver_task = asyncio.create_task(resolver())
    decision = await request_task
    await resolver_task

    assert decision == "approve"
    assert bus.broadcasted[0] == (
        "t1",
        {
            "event": "approval_request",
            "action_id": "a1",
            "tool": "run_command",
            "args": {"command": "rm -rf /"},
            "level": "critical",
            "timeout_seconds": 5.0,
        },
    )


@pytest.mark.asyncio
async def test_hub_request_times_out_with_timeout():
    bus = FakeBus()
    hub = ApprovalHub(bus=bus, timeout=0.05)

    decision = await hub.request("t1", {"action_id": "a1", "tool": "x", "args": {}, "level": "dangerous"})

    assert decision == "timeout"


def test_hub_resolve_unknown_action_is_noop():
    hub = ApprovalHub(bus=FakeBus(), timeout=5.0)
    hub.resolve("missing", "approve")
    assert hub._waiters == {}


@pytest.mark.asyncio
async def test_hub_decision_during_broadcast_is_not_lost():
    """A client may resolve as soon as it receives approval_request.

    The waiter must be registered before the broadcast is sent, otherwise the
    decision is dropped and the loop waits out the timeout to get ``reject``.
    """
    holder: dict[str, ApprovalHub] = {}

    class ResolvingBus(FakeBus):
        async def broadcast(self, task_id: str, payload: dict) -> None:
            await super().broadcast(task_id, payload)
            holder["hub"].resolve(payload["action_id"], "approve")

    hub = ApprovalHub(bus=ResolvingBus(), timeout=5.0)
    holder["hub"] = hub

    decision = await hub.request(
        "t1", {"action_id": "a1", "tool": "x", "args": {}, "level": "dangerous"}
    )

    assert decision == "approve"
