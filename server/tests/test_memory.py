from kl_server.memory.store import MemoryStore


def test_memory_stores_and_finds_by_tag(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.add("project", "decision", ["auth"], "use tokens")
    result = store.find(["auth"])
    assert result == ["use tokens"]
