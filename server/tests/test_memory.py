import pytest

from kl_server.memory.store import MemoryStore


@pytest.mark.asyncio
async def test_memory_stores_and_finds_by_tag(tmp_path):
    async with MemoryStore(tmp_path / "memory.db") as store:
        await store.add("project", "decision", ["auth"], "use tokens")

        assert await store.find(["auth"]) == ["use tokens"]


@pytest.mark.asyncio
async def test_no_matching_tags_returns_empty(tmp_path):
    async with MemoryStore(tmp_path / "memory.db") as store:
        await store.add("project", "decision", ["auth"], "use tokens")

        assert await store.find(["config"]) == []


@pytest.mark.asyncio
async def test_multiple_query_tags_match_one_entry_once(tmp_path):
    async with MemoryStore(tmp_path / "memory.db") as store:
        await store.add("project", "decision", ["auth", "session"], "one entry")

        assert await store.find(["session", "auth"]) == ["one entry"]


@pytest.mark.asyncio
async def test_duplicate_and_empty_tags(tmp_path):
    async with MemoryStore(tmp_path / "memory.db") as store:
        await store.add("project", "decision", ["auth", "auth"], "duplicate tags")
        await store.add("project", "decision", [], "no tags")

        assert await store.find(["auth", "auth"]) == ["duplicate tags"]
        assert await store.find([]) == []


@pytest.mark.asyncio
async def test_tags_with_commas_are_stored_unambiguously(tmp_path):
    async with MemoryStore(tmp_path / "memory.db") as store:
        await store.add("project", "decision", ["a,b", "auth"], "comma tag")

        assert await store.find(["a,b"]) == ["comma tag"]
        assert await store.find(["a"]) == []


@pytest.mark.asyncio
async def test_memory_persists_across_reopen(tmp_path):
    path = tmp_path / "memory.db"
    store = MemoryStore(path)
    await store.connect()
    await store.add("project", "decision", ["auth"], "use tokens")
    await store.close()
    await store.close()

    reopened = MemoryStore(path)
    await reopened.connect()
    try:
        assert await reopened.find(["auth"]) == ["use tokens"]
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_state_persists_across_reopen(tmp_path):
    path = tmp_path / "memory.db"
    store = MemoryStore(path)
    await store.connect()
    await store.set_state("session:s1", "subtasks", '{"subtasks":[]}')
    await store.close()

    reopened = MemoryStore(path)
    await reopened.connect()
    try:
        assert await reopened.get_state("session:s1", "subtasks") == '{"subtasks":[]}'
        assert await reopened.get_state("session:s2", "subtasks") is None
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_delete_state_removes_only_requested_key(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    await store.connect()
    try:
        await store.set_state("session:s1", "subtasks", "[]")
        await store.set_state("session:s1", "other", "x")
        await store.set_state("session:s2", "subtasks", "[]")

        await store.delete_state("session:s1", "subtasks")

        assert await store.get_state("session:s1", "subtasks") is None
        assert await store.get_state("session:s1", "other") == "x"
        assert await store.get_state("session:s2", "subtasks") == "[]"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_context_manager_close_is_idempotent(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    async with store:
        await store.add("project", "decision", ["auth"], "use tokens")

    await store.close()
    await store.close()
