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

    assert alive.sent == [{"task_id": "t1", "event": "loop_start"}]
    assert dead.sent == []
    # dead connection removed from the set; next broadcast only reaches alive
    await bus.broadcast("t1", {"event": "second"})
    assert len(alive.sent) == 2

    await bus.unregister("t1", alive)
    await bus.broadcast("t1", {"event": "third"})
    assert len(alive.sent) == 2


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
        },
    )


@pytest.mark.asyncio
async def test_hub_request_times_out_with_reject():
    bus = FakeBus()
    hub = ApprovalHub(bus=bus, timeout=0.05)

    decision = await hub.request("t1", {"action_id": "a1", "tool": "x", "args": {}, "level": "dangerous"})

    assert decision == "reject"


def test_hub_resolve_unknown_action_is_noop():
    hub = ApprovalHub(bus=FakeBus(), timeout=5.0)
    hub.resolve("missing", "approve")
    assert hub._waiters == {}
