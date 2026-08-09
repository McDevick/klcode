import yaml
import json

import pytest
from time import sleep

from fastapi.testclient import TestClient

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.config.credentials import InMemoryCredentialStore
from kl_server.models.task import Session, Task, TaskStatus


def make_client():
    return TestClient(create_app())


def make_deps_client(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    return TestClient(create_app(deps=deps))


def test_lifespan_closes_database_and_memory(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))
    with client:
        assert client.get("/health").status_code == 200

    assert deps.db.conn is None
    assert deps.memory.conn is None


class TrackingMcpAdapter:
    def __init__(self):
        self.closed = False

    async def close(self):
        self.closed = True


class DiscoveryMcpAdapter(TrackingMcpAdapter):
    servers = {"demo": {}}

    async def list_tools(self, server):
        return [
            {
                "name": "echo",
                "description": "echo text",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }
        ]


def test_lifespan_closes_mcp_adapter(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    tracker = TrackingMcpAdapter()
    deps.mcp = tracker

    client = TestClient(create_app(deps=deps))
    with client:
        assert client.get("/health").status_code == 200

    assert tracker.closed is True


def test_lifespan_registers_mcp_tools(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    deps.mcp = DiscoveryMcpAdapter()

    client = TestClient(create_app(deps=deps))
    with client:
        names = {item["name"] for item in deps.tool_registry.catalog()}

    assert "mcp_demo_echo" in names
    assert deps.mcp.closed is True


def test_mcp_management_add_list_refresh_remove(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    deps.mcp = DiscoveryMcpAdapter()

    client = TestClient(create_app(deps=deps))
    with client:
        added = client.post(
            "/api/v1/mcp",
            json={"name": "demo", "url": "http://localhost:9999"},
        )
        assert added.status_code == 200
        assert added.json()["name"] == "demo"
        assert added.json()["tools"][0]["name"] == "mcp_demo_echo"

        listed = client.get("/api/v1/mcp")
        assert listed.status_code == 200
        assert listed.json()[0]["url"] == "http://localhost:9999"
        assert listed.json()[0]["tools"][0]["remote_name"] == "echo"

        refreshed = client.post("/api/v1/mcp/demo/refresh")
        assert refreshed.status_code == 200
        assert refreshed.json()["tools"][0]["name"] == "mcp_demo_echo"

        deleted = client.delete("/api/v1/mcp/demo")
        assert deleted.status_code == 204
        assert client.get("/api/v1/mcp").json() == []
        assert not any(
            item["name"] == "mcp_demo_echo"
            for item in deps.tool_registry.catalog()
        )


def create_session(client, workspace="C:\\work", name=None):
    payload = {"workspace": workspace}
    if name is not None:
        payload["name"] = name
    return client.post("/api/v1/sessions", json=payload)


def test_sessions_list_starts_empty():
    client = make_client()

    response = client.get("/api/v1/sessions")

    assert response.status_code == 200
    assert response.json() == []


def test_model_config_lists_configured_provider_models(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_provider: deepseek\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-v4-flash\n"
        "    models:\n"
        "      - deepseek-v4-flash\n"
        "      - deepseek-v4-pro\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))

    with client:
        response = client.get("/api/v1/config/model")

    assert response.status_code == 200
    models = {
        item["model"]
        for item in response.json()["available"]
        if item["provider"] == "deepseek"
    }
    assert models == {"deepseek-v4-flash", "deepseek-v4-pro"}


def test_corrupt_database_returns_backup_path_and_blocks_writes(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    (tmp_path / "kl.db").write_text("not a sqlite database", encoding="utf-8")
    client = TestClient(create_app(deps=deps))

    with client:
        response = client.get("/api/v1/sessions")

    assert response.status_code == 503
    assert "backup:" in response.json()["detail"]
    assert "writes blocked" in response.json()["detail"]


def test_skills_endpoint_lists_global_skills(tmp_path):
    client = make_deps_client(tmp_path)
    skill_dir = tmp_path / "skills" / "leetcode"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "# LeetCode\n解决 LeetCode C++ 题目",
        encoding="utf-8",
    )

    response = client.get("/api/v1/skills")

    assert response.status_code == 200
    assert response.json() == [
        {"name": "leetcode", "description": "解决 LeetCode C++ 题目"}
    ]


def test_session_create_get_and_list_returns_generated_id():
    client = make_client()

    created = create_session(client, name="main")
    assert created.status_code == 200
    created_body = created.json()
    assert created_body["id"]
    assert created_body["workspace"] == "C:\\work"
    assert created_body["name"] == "main"
    assert created_body["status"] == "active"

    session_id = created_body["id"]
    fetched = client.get(f"/api/v1/sessions/{session_id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == session_id

    listed = client.get("/api/v1/sessions")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [session_id]


def test_session_rename_close_and_delete():
    client = make_client()
    session_id = create_session(client).json()["id"]

    renamed = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"name": "renamed"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "renamed"
    assert client.get(f"/api/v1/sessions/{session_id}").json()["name"] == "renamed"

    closed = client.post(f"/api/v1/sessions/{session_id}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.get(f"/api/v1/sessions/{session_id}").json()["status"] == "closed"

    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404



@pytest.mark.asyncio
async def test_session_close_rejects_running_task(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    task_id = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "running"},
    ).json()["id"]
    deps = client.app.state.deps
    task = await deps.tasks.get(task_id)
    task.status = TaskStatus.RUNNING
    await deps.tasks.update(task)

    response = client.post(f"/api/v1/sessions/{session_id}/close")

    assert response.status_code == 409
    assert client.get(f"/api/v1/sessions/{session_id}").json()["status"] == "active"


@pytest.mark.asyncio
async def test_session_delete_rejects_running_task_then_allows_after_abort(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    task_id = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "running"},
    ).json()["id"]
    deps = client.app.state.deps
    task = await deps.tasks.get(task_id)
    task.status = TaskStatus.PAUSED
    await deps.tasks.update(task)

    rejected = client.delete(f"/api/v1/sessions/{session_id}")
    assert rejected.status_code == 409
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 200

    task = await deps.tasks.get(task_id)
    task.status = TaskStatus.CANCELED
    await deps.tasks.update(task)
    deleted = client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404


def test_session_history_replays_audit_events(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    task = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "hello"},
    ).json()
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "loop_start",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "task_id": task["id"],
                        "payload": {"task": "hello"},
                    }
                ),
                json.dumps(
                    {
                        "event": "agent_message",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "task_id": task["id"],
                        "payload": {"text": "我先看一下"},
                    }
                ),
                json.dumps(
                    {
                        "event": "tool_result",
                        "timestamp": "2026-01-01T00:00:02+00:00",
                        "task_id": task["id"],
                        "payload": {
                            "tool": "list_dir",
                            "ok": True,
                            "args": {"path": "."},
                            "output": "demo.cpp",
                        },
                    }
                ),
                json.dumps(
                    {
                        "event": "llm_result",
                        "timestamp": "2026-01-01T00:00:03+00:00",
                        "task_id": task["id"],
                        "payload": {"text": "DONE: 完成"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    history = client.get(f"/api/v1/sessions/{session_id}/history")

    assert history.status_code == 200
    assert [item["type"] for item in history.json()] == ["user", "agent", "tool", "agent"]
    assert history.json()[0]["content"] == "hello"
    assert history.json()[1]["content"] == "我先看一下"
    assert history.json()[2]["name"] == "list_dir"
    assert history.json()[3]["content"] == "完成"


@pytest.mark.asyncio
async def test_session_history_uses_full_task_summary(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    task = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "hello"},
    ).json()
    deps = client.app.state.deps
    stored = await deps.tasks.get(task["id"])
    stored.summary = "DONE: 这是完整回答"
    await deps.tasks.update(stored)

    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        json.dumps(
            {
                "event": "llm_result",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "task_id": task["id"],
                "payload": {"text": "这是被截断的回答"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    history = client.get(f"/api/v1/sessions/{session_id}/history").json()

    assert history[-1]["content"] == "这是完整回答"
    assert "被截断" not in history[-1]["content"]


@pytest.mark.asyncio
async def test_session_feedback_endpoint_lists_feedback_memory(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    memory = client.app.state.deps.memory
    await memory.add(
        session_id,
        "feedback",
        [session_id],
        "run_tests: test_failure: assert failed",
    )

    response = client.get(f"/api/v1/sessions/{session_id}/feedback")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "content": "run_tests: test_failure: assert failed",
            "tags": [session_id],
        }
    ]


def test_session_history_reads_task_history_partition(tmp_path):

    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    task_id = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "hello"},
    ).json()["id"]
    deps = client.app.state.deps
    deps.logger.write("loop_start", {"task": "hello"}, task_id)
    deps.logger.write("agent_message", {"text": "world"}, task_id)
    deps.logger.write(
        "tool_result",
        {
            "tool": "run_command",
            "ok": True,
            "args": {"command": "pytest --token secret-value"},
            "output": "passed",
        },
        task_id,
    )

    history = client.get(f"/api/v1/sessions/{session_id}/history").json()

    assert any(item["type"] == "user" and item["content"] == "hello" for item in history)
    assert any(item["type"] == "agent" and item["content"] == "world" for item in history)
    tool = next(item for item in history if item["type"] == "tool")
    assert "pytest --token" in tool["args"]["command"]
    assert "secret-value" not in tool["args"]["command"]
    assert "[REDACTED]" in tool["args"]["command"]


@pytest.mark.asyncio
async def test_delete_session_cleans_task_manage_state(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    deps = client.app.state.deps
    memory = deps.memory
    await memory.set_state(f"session:{session_id}", "subtasks", "[]")
    await memory.set_state(f"session:{session_id}", "continuation_context", "{}")
    await memory.set_state(f"session:{session_id}", "user_instructions", "[]")
    await memory.add(session_id, "feedback", [session_id], "old feedback")
    task_id = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "history task"},
    ).json()["id"]
    history_path = deps.logger.history_path(task_id)
    assert history_path is not None
    deps.logger.write("loop_start", {"task": "history task"}, task_id)
    assert history_path.exists()
    output_dir = deps.executor.output_dir
    session_output = output_dir / session_id
    session_output.mkdir(parents=True)
    (session_output / "big.txt").write_text("full output", encoding="utf-8")
    manifest = output_dir / "MANIFEST.jsonl"
    manifest.write_text(
        json.dumps({"session_id": session_id, "output_file": "x"}) + "\n",
        encoding="utf-8",
    )

    deleted = client.delete(f"/api/v1/sessions/{session_id}")

    assert deleted.status_code == 204
    assert await memory.get_state(f"session:{session_id}", "subtasks") is None
    assert await memory.get_state(f"session:{session_id}", "continuation_context") is None
    assert await memory.get_state(f"session:{session_id}", "user_instructions") is None
    assert await memory.find([session_id]) == []
    assert not session_output.exists()
    assert session_id not in manifest.read_text(encoding="utf-8")
    assert not history_path.exists()


@pytest.mark.asyncio
async def test_context_status_and_compact(tmp_path):
    client = make_deps_client(tmp_path)
    client.app.state.deps.config.default_provider = "mock"
    session_id = create_session(client, str(tmp_path)).json()["id"]
    memory = client.app.state.deps.memory
    await memory.add(session_id, "context_summary", [session_id], "some remembered context")

    status = client.get(f"/api/v1/sessions/{session_id}/context")
    assert status.status_code == 200
    body = status.json()
    assert body["max_tokens"] == 20000
    assert {section["name"] for section in body["sections"]} == {"system", "memory", "history"}
    assert body["remaining_tokens"] >= 0

    compacted = client.post(f"/api/v1/sessions/{session_id}/context/compact")
    assert compacted.status_code == 200
    assert compacted.json()["max_tokens"] == 20000


@pytest.mark.asyncio
async def test_compact_context_reduces_history_status(tmp_path):
    client = make_deps_client(tmp_path)
    client.app.state.deps.config.default_provider = "mock"
    session_id = create_session(client, str(tmp_path)).json()["id"]
    task = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "hello"},
    ).json()
    audit_path = tmp_path / "audit.jsonl"
    audit_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event": "loop_start",
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "task_id": task["id"],
                        "payload": {"task": "hello"},
                    }
                ),
                json.dumps(
                    {
                        "event": "agent_message",
                        "timestamp": "2026-01-01T00:00:01+00:00",
                        "task_id": task["id"],
                        "payload": {"text": "I did something"},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    before = client.get(f"/api/v1/sessions/{session_id}/context").json()
    history_before = next(section["tokens"] for section in before["sections"] if section["name"] == "history")
    assert history_before > 0

    client.post(f"/api/v1/sessions/{session_id}/context/compact")

    after = client.get(f"/api/v1/sessions/{session_id}/context").json()
    history_after = next(section["tokens"] for section in after["sections"] if section["name"] == "history")
    assert history_after == 0


def test_missing_session_returns_not_found():
    client = make_client()

    assert client.get("/api/v1/sessions/missing").status_code == 404
    assert client.patch("/api/v1/sessions/missing", json={"name": "x"}).status_code == 404
    assert client.post("/api/v1/sessions/missing/close").status_code == 404
    assert client.delete("/api/v1/sessions/missing").status_code == 404


def test_task_create_and_get_returns_generated_id():
    client = make_client()

    created = client.post(
        "/api/v1/tasks",
        json={"session_id": "s1", "description": "fix"},
    )
    assert created.status_code == 200
    task = created.json()
    assert task["id"]
    assert task["session_id"] == "s1"
    assert task["description"] == "fix"
    assert task["status"] == "pending"

    fetched = client.get(f"/api/v1/tasks/{task['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == task


def test_missing_task_returns_not_found():
    client = make_client()

    response = client.get("/api/v1/tasks/missing")

    assert response.status_code == 404


def test_task_create_with_missing_session_returns_404_with_deps(tmp_path):
    client = make_deps_client(tmp_path)

    response = client.post(
        "/api/v1/tasks",
        json={"session_id": "missing", "description": "orphan task"},
    )

    assert response.status_code == 404


def test_task_create_rejects_missing_workspace(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path / "missing")},
    ).json()["id"]

    response = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "hello"},
    )

    assert response.status_code == 400
    assert "workspace does not exist" in response.json()["detail"]


@pytest.mark.asyncio
async def test_task_instruction_endpoint_adds_to_loop(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path)},
    ).json()["id"]
    task = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "hello"},
    ).json()

    response = client.post(
        f"/api/v1/tasks/{task['id']}/instructions",
        json={"instruction": "请先运行测试"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "instruction_added"
    assert client.app.state.deps.loop._instructions[task["id"]] == [
        "请先运行测试"
    ]
    notes = await client.app.state.deps.memory.find(
        [session_id],
        kinds=["user_note"],
    )
    assert notes == ["请先运行测试"]


def test_task_create_with_existing_session_succeeds_with_deps(tmp_path):
    client = make_deps_client(tmp_path)

    session = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path), "name": "main"},
    ).json()
    response = client.post(
        "/api/v1/tasks",
        json={"session_id": session["id"], "description": "valid task"},
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == session["id"]


def test_task_create_accepts_workspace_mode_and_branch(tmp_path):
    client = make_deps_client(tmp_path)

    session = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path)},
    ).json()
    created = client.post(
        "/api/v1/tasks",
        json={
            "session_id": session["id"],
            "description": "unmanaged task",
            "workspace_mode": "unmanaged",
            "branch": "feature/foo",
        },
    )

    assert created.status_code == 200
    body = created.json()
    assert body["workspace_mode"] == "unmanaged"
    assert body["branch"] == "feature/foo"

    invalid = client.post(
        "/api/v1/tasks",
        json={
            "session_id": session["id"],
            "description": "bad mode",
            "workspace_mode": "bogus",
        },
    )
    assert invalid.status_code == 422


def test_config_check_reports_mock_provider():
    client = make_client()

    response = client.post("/api/v1/config/check")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "mock" in body["providers"]


def test_provider_list_and_add():
    client = make_client()

    listed = client.get("/api/v1/providers")
    assert listed.status_code == 200
    assert any(item["name"] == "mock" for item in listed.json())

    provider = {
        "name": "acme",
        "type": "openai-compatible",
        "base_url": "http://127.0.0.1:9999/v1",
        "default_model": "gpt-test",
    }
    added = client.post("/api/v1/providers", json=provider)
    assert added.status_code == 200
    assert added.json()["name"] == "acme"

    listed = client.get("/api/v1/providers")
    assert any(item["name"] == "acme" for item in listed.json())


def test_models_route_includes_mock_model():
    client = make_client()

    response = client.get("/api/v1/models")

    assert response.status_code == 200
    assert any(item["model"] == "mock-model" for item in response.json())


def test_key_routes_only_return_configured_status_and_never_secret():
    client = make_client()
    secret = "sk-super-secret"

    configured = client.post("/api/v1/keys/openai", json={"secret": secret})
    assert configured.status_code == 200
    assert configured.json() == {"configured": True}
    assert secret not in configured.text

    status = client.get("/api/v1/keys/openai")
    assert status.status_code == 200
    assert status.json() == {"configured": True}
    assert secret not in status.text

    listed = client.get("/api/v1/keys")
    assert listed.status_code == 200
    assert "openai" in listed.json()["configured"]
    assert secret not in listed.text

    cleared = client.delete("/api/v1/keys/openai")
    assert cleared.status_code == 200
    assert cleared.json() == {"configured": False}
    assert secret not in cleared.text
    assert client.get("/api/v1/keys/openai").json() == {"configured": False}


def test_key_routes_persist_to_credential_store_with_deps(tmp_path):
    client = make_deps_client(tmp_path)
    deps = client.app.state.deps

    configured = client.post("/api/v1/keys/openai", json={"secret": "sk-real-secret"})
    assert configured.status_code == 200
    assert configured.json() == {"configured": True}
    assert deps.credentials.has("openai") is True

    assert client.get("/api/v1/keys/openai").json() == {"configured": True}
    assert "openai" in client.get("/api/v1/keys").json()["configured"]

    cleared = client.delete("/api/v1/keys/openai")
    assert cleared.status_code == 200
    assert deps.credentials.has("openai") is False


def test_provider_add_persists_config_and_registers_with_deps(tmp_path):
    client = make_deps_client(tmp_path)
    deps = client.app.state.deps
    provider = {
        "name": "acme",
        "type": "openai-compatible",
        "base_url": "http://127.0.0.1:9999/v1",
        "default_model": "gpt-test",
    }

    added = client.post("/api/v1/providers", json=provider)

    assert added.status_code == 200
    assert added.json()["name"] == "acme"
    assert deps.provider_registry.get("acme") is not None
    assert "acme" in deps.config.providers
    assert deps.config.providers["acme"].base_url == "http://127.0.0.1:9999/v1"

    listed = client.get("/api/v1/providers")
    assert any(item["name"] == "acme" for item in listed.json())


def test_provider_add_writes_config_yaml_with_deps(tmp_path):
    client = make_deps_client(tmp_path)
    provider = {
        "name": "acme",
        "type": "openai-compatible",
        "base_url": "http://127.0.0.1:9999/v1",
        "default_model": "gpt-test",
    }

    client.post("/api/v1/providers", json=provider)

    config_path = tmp_path / "config.yaml"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "acme" in content
    assert "http://127.0.0.1:9999/v1" in content


def test_provider_test_calls_real_provider_endpoint(tmp_path):
    client = make_deps_client(tmp_path)

    response = client.post("/api/v1/providers/mock/test")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "provider": "mock",
        "model": "mock-model",
    }


def test_create_session_after_restart_avoids_id_conflict(tmp_path):
    # 第一次启动：创建 s1 并持久化
    first = make_deps_client(tmp_path)
    created = first.post("/api/v1/sessions", json={"workspace": str(tmp_path)})
    assert created.status_code == 200
    assert created.json()["id"] == "s1"

    # 模拟服务重启：新 deps + 新 app，但同一个数据库文件
    restarted = make_deps_client(tmp_path)
    created_again = restarted.post("/api/v1/sessions", json={"workspace": str(tmp_path)})

    assert created_again.status_code == 200
    assert created_again.json()["id"] != "s1"


def test_create_task_after_restart_avoids_id_conflict(tmp_path):
    first = make_deps_client(tmp_path)
    session = first.post("/api/v1/sessions", json={"workspace": str(tmp_path)}).json()
    task = first.post(
        "/api/v1/tasks", json={"session_id": session["id"], "description": "first"}
    ).json()
    assert task["id"] == "t1"

    restarted = make_deps_client(tmp_path)
    session_again = restarted.post(
        "/api/v1/sessions", json={"workspace": str(tmp_path)}
    ).json()
    task_again = restarted.post(
        "/api/v1/tasks",
        json={"session_id": session_again["id"], "description": "second"},
    )

    assert task_again.status_code == 200
    assert task_again.json()["id"] != "t1"


def test_route_state_is_isolated_per_app_instance():
    client_a = make_client()
    client_b = make_client()

    session_id = create_session(client_a).json()["id"]
    task = client_a.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "isolated"},
    ).json()
    client_a.post("/api/v1/providers", json={
        "name": "acme",
        "type": "openai-compatible",
        "base_url": "http://127.0.0.1:9999/v1",
        "default_model": "gpt-test",
    })
    client_a.post("/api/v1/keys/openai", json={"secret": "sk-secret"})

    assert client_b.get("/api/v1/sessions").json() == []
    assert client_b.get(f"/api/v1/tasks/{task['id']}").status_code == 404
    assert all(item["name"] != "acme" for item in client_b.get("/api/v1/providers").json())
    assert client_b.get("/api/v1/keys/openai").json() == {"configured": False}


def test_new_routes_are_protected_by_auth_middleware():
    client = TestClient(create_app(auth_token="s3cret"))

    unauthorized = client.post(
        "/api/v1/sessions",
        json={"workspace": "C:\\work"},
    )
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/api/v1/sessions",
        json={"workspace": "C:\\work"},
        headers={"Authorization": "Bearer s3cret"},
    )
    assert authorized.status_code == 200


def test_config_model_get_returns_current_default(tmp_path):
    client = make_deps_client(tmp_path)

    response = client.get("/api/v1/config/model")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deepseek"
    assert body["model"] == "deepseek-v4-flash"
    assert body["max_context"] == 20000
    assert {
        "provider": "mock",
        "model": "mock-model",
        "base_url": "",
        "max_context": 20000,
    } in body["available"]
    assert {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "base_url": "https://api.deepseek.com",
        "max_context": 20000,
    } in body["available"]


def test_config_model_set_switches_provider_and_persists(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_provider: mock\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n"
        "    credential_ref: deepseek\n",
        encoding="utf-8",
    )
    credentials = InMemoryCredentialStore()
    credentials.set("deepseek", "sk-test")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=credentials,
    )
    client = TestClient(create_app(deps=deps))

    response = client.post(
        "/api/v1/config/model",
        json={"provider": "deepseek", "model": "deepseek-reasoner"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "deepseek"
    assert body["model"] == "deepseek-reasoner"
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["default_provider"] == "deepseek"
    assert persisted["default_model"] == "deepseek-reasoner"


def test_config_model_set_clears_override_uses_provider_default(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_provider: mock\n"
        "default_model: stale\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n"
        "    credential_ref: deepseek\n",
        encoding="utf-8",
    )
    credentials = InMemoryCredentialStore()
    credentials.set("deepseek", "sk-test")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=credentials,
    )
    client = TestClient(create_app(deps=deps))

    response = client.post("/api/v1/config/model", json={"provider": "deepseek"})

    assert response.status_code == 200
    assert response.json()["model"] == "deepseek-chat"
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert persisted["default_provider"] == "deepseek"
    assert persisted["default_model"] == ""


def test_config_model_set_unknown_provider_returns_404(tmp_path):
    client = make_deps_client(tmp_path)

    response = client.post("/api/v1/config/model", json={"provider": "missing"})

    assert response.status_code == 404
    assert response.json()["detail"] == "provider not found"


def test_config_model_set_allows_unavailable_provider(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_provider: mock\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n"
        "    credential_ref: deepseek\n",
        encoding="utf-8",
    )
    # 不设置 deepseek 凭证 → provider 存在但不可用，仍允许切换
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))

    response = client.post("/api/v1/config/model", json={"provider": "deepseek"})

    assert response.status_code == 200
    assert response.json()["provider"] == "deepseek"
    assert response.json()["model"] == "deepseek-chat"



def test_mcp_list_reports_discovery_error(tmp_path):
    client = make_deps_client(tmp_path)
    deps = client.app.state.deps
    deps.mcp.servers["bad"] = {"url": "http://127.0.0.1:1"}
    deps.mcp.last_errors["bad"] = "boom"

    records = client.get("/api/v1/mcp").json()

    assert records[0]["status"] == "error"
    assert records[0]["error"] == "boom"


def test_config_check_reports_configured_providers(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))

    response = client.post("/api/v1/config/check")

    assert response.status_code == 200
    assert "deepseek" in response.json()["providers"]


def test_delete_session_with_tasks_succeeds(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    created = client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "fix"},
    )
    assert created.status_code == 200

    deleted = client.delete(f"/api/v1/sessions/{session_id}")

    assert deleted.status_code == 204
    assert client.get(f"/api/v1/sessions/{session_id}").status_code == 404


def test_list_sessions_includes_task_count(tmp_path):
    client = make_deps_client(tmp_path)
    session_id = create_session(client, str(tmp_path)).json()["id"]
    client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "one task"},
    )
    client.post(
        "/api/v1/tasks",
        json={"session_id": session_id, "description": "two task"},
    )

    listed = client.get("/api/v1/sessions")

    assert listed.status_code == 200
    record = next(item for item in listed.json() if item["id"] == session_id)
    assert record["task_count"] == 2


def test_set_key_refreshes_registered_provider_api_key(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com\n"
        "    default_model: deepseek-chat\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))
    provider = deps.provider_registry.get("deepseek")
    assert provider.api_key is None  # 注册时无 credential_ref → 无 key

    response = client.post("/api/v1/keys/deepseek", json={"secret": "sk-new"})

    assert response.status_code == 200
    assert provider.api_key == "sk-new"
    assert provider.openai.api_key == "sk-new"
    config_text = config_path.read_text(encoding="utf-8")
    assert "credential_ref: deepseek" in config_text
    assert "sk-new" not in config_text


def test_set_key_does_not_persist_secret_on_model_switch(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_provider: deepseek\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com\n"
        "    default_model: deepseek-chat\n"
        "    api_key: null\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))

    with client:
        assert client.post(
            "/api/v1/keys/deepseek",
            json={"secret": "sk-protected"},
        ).status_code == 200
        assert client.post(
            "/api/v1/config/model",
            json={"provider": "deepseek", "model": "deepseek-chat"},
        ).status_code == 200

    config_text = config_path.read_text(encoding="utf-8")
    assert "sk-protected" not in config_text


class RestartedCredentialStore:
    def __init__(self):
        self._secrets = {"deepseek": "sk-restored"}

    def set(self, ref, secret):
        self._secrets[ref] = secret

    def get(self, ref):
        return self._secrets.get(ref)

    def has(self, ref):
        return ref in self._secrets

    def clear(self, ref):
        self._secrets.pop(ref, None)

    def safe_snapshot(self):
        return {}


def test_list_keys_detects_keyring_keys_after_restart(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com\n"
        "    default_model: deepseek-chat\n"
        "    credential_ref: deepseek\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=RestartedCredentialStore(),
    )
    client = TestClient(create_app(deps=deps))

    with client:
        response = client.get("/api/v1/keys")

    assert response.status_code == 200
    assert response.json() == {"configured": ["deepseek"]}


def test_daemon_status_reports_source_and_ws_connections(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    client = TestClient(create_app(deps=deps, daemon_source="auto"))
    with client:
        status = client.get("/daemon/status").json()
        assert status == {"source": "auto", "running_tasks": 0, "ws_connections": 0}
        with client.websocket_connect("/ws/daemon") as websocket:
            assert websocket
            status = client.get("/daemon/status").json()
            assert status["ws_connections"] == 1


@pytest.mark.asyncio
async def test_daemon_status_counts_running_tasks(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    await deps.sessions.create(
        Session(id="s1", workspace=str(tmp_path))
    )
    await deps.tasks.create(
        Task(
            id="t1",
            session_id="s1",
            description="long task",
            status=TaskStatus.RUNNING,
        )
    )
    client = TestClient(create_app(deps=deps))
    with client:
        status = client.get("/daemon/status").json()
        assert status["running_tasks"] == 1


def test_auto_daemon_idle_reaper_exits(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    app = create_app(deps=deps, daemon_source="auto", idle_timeout=0.1)
    exited: list[bool] = []
    app.state.idle_exit = lambda: exited.append(True)
    client = TestClient(app)
    with client:
        sleep(0.6)
    assert exited


def test_manual_daemon_not_reaped(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    app = create_app(deps=deps, daemon_source="manual", idle_timeout=0.1)
    exited: list[bool] = []
    app.state.idle_exit = lambda: exited.append(True)
    client = TestClient(app)
    with client:
        sleep(0.6)
    assert not exited


@pytest.mark.asyncio
async def test_auto_daemon_task_keepalive(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    await deps.sessions.create(Session(id="s1", workspace=str(tmp_path)))
    await deps.tasks.create(
        Task(id="t1", session_id="s1", description="long", status=TaskStatus.RUNNING)
    )
    app = create_app(deps=deps, daemon_source="auto", idle_timeout=0.1)
    exited: list[bool] = []
    app.state.idle_exit = lambda: exited.append(True)
    client = TestClient(app)
    with client:
        sleep(0.6)
    assert not exited


def test_auto_daemon_ws_keepalive(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    app = create_app(deps=deps, daemon_source="auto", idle_timeout=0.1)
    exited: list[bool] = []
    app.state.idle_exit = lambda: exited.append(True)
    client = TestClient(app)
    with client:
        with client.websocket_connect("/ws/daemon") as websocket:
            assert websocket
            sleep(0.6)
        assert not exited



def test_approval_hub_uses_config_timeout(tmp_path):
    deps = build_app_dependencies(
        config_path=tmp_path / "config.yaml",
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    deps.config.guardrail.approval_timeout_seconds = 123.0
    client = TestClient(create_app(deps=deps))

    assert client.app.state.approval_hub.timeout == 123.0