from types import SimpleNamespace

from fastapi.testclient import TestClient

from kl_server.api.app import create_app
from kl_server.bootstrap import build_app_dependencies
from kl_server.config.credentials import InMemoryCredentialStore
from kl_server.core.context import LLMSummarizer


def test_bootstrap_registers_providers_tools_and_managers(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    credentials = InMemoryCredentialStore()
    credentials.set("openai", "test-key")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=credentials,
    )

    assert deps.provider_registry.get("mock") is not None
    assert deps.provider_registry.get("openai") is not None
    assert deps.tool_registry.get("read_file") is not None
    assert deps.tool_registry.get("task_manage") is not None
    assert deps.sessions is not None
    assert deps.tasks is not None


def test_bootstrap_wires_api_routes_to_deps(tmp_path):
    class FakeSessions:
        def __init__(self):
            self.store = {}

        async def create(self, session):
            self.store[session.id] = session

        async def list(self):
            return list(self.store.values())

        async def get(self, session_id):
            if session_id not in self.store:
                raise KeyError(session_id)
            return self.store[session_id]

        async def update(self, session):
            if session.id not in self.store:
                raise KeyError(session.id)
            self.store[session.id] = session

        async def delete(self, session_id):
            if session_id not in self.store:
                raise KeyError(session_id)
            del self.store[session_id]

    class FakeTasks:
        def __init__(self):
            self.store = {}

        async def create(self, task):
            self.store[task.id] = task

        async def list(self):
            return list(self.store.values())

        async def get(self, task_id):
            if task_id not in self.store:
                raise KeyError(task_id)
            return self.store[task_id]

        async def count_by_session(self, session_id):
            return sum(1 for task in self.store.values() if task.session_id == session_id)

    deps = SimpleNamespace(
        sessions=FakeSessions(),
        tasks=FakeTasks(),
        config=SimpleNamespace(default_provider="mock", default_model=""),
    )
    client = TestClient(create_app(deps=deps))

    created = client.post(
        "/api/v1/sessions",
        json={"workspace": str(tmp_path), "name": "bootstrap"},
    )
    assert created.status_code == 200
    session = created.json()
    assert session["id"]
    assert deps.sessions.store[session["id"]].workspace == str(tmp_path)

    listed = client.get("/api/v1/sessions")
    assert [item["id"] for item in listed.json()] == [session["id"]]
    assert listed.json()[0]["task_count"] == 0

    fetched = client.get(f"/api/v1/sessions/{session['id']}")
    assert fetched.json() == session

    renamed = client.patch(f"/api/v1/sessions/{session['id']}", json={"name": "renamed"})
    assert renamed.json()["name"] == "renamed"
    assert deps.sessions.store[session["id"]].name == "renamed"

    closed = client.post(f"/api/v1/sessions/{session['id']}/close")
    assert closed.json()["status"] == "closed"
    assert deps.sessions.store[session["id"]].status == "closed"

    task = client.post(
        "/api/v1/tasks",
        json={"session_id": session["id"], "description": "compose server"},
    )
    assert task.status_code == 200
    assert deps.tasks.store[task.json()["id"]].description == "compose server"
    fetched_task = client.get(f"/api/v1/tasks/{task.json()['id']}")
    assert fetched_task.json() == task.json()

    deleted = client.delete(f"/api/v1/sessions/{session['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/sessions/{session['id']}").status_code == 404


def test_bootstrap_sandbox_allows_git_and_curl(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )
    sandbox = deps.executor.guardrail.sandbox

    assert sandbox.allow_command("git status") is True
    assert sandbox.allow_command("curl -I https://example.com") is True
    assert sandbox.allow_command("rm -rf .") is False
    assert sandbox.allow_command("docker ps") is False


def test_bootstrap_starts_with_missing_provider_credential(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )

    assert deps.provider_registry.get("mock") is not None
    assert deps.config_error == "credential not found: openai"

    client = TestClient(create_app(deps=deps))
    response = client.post("/api/v1/config/check")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["error"] == "credential not found: openai"


def test_bootstrap_loop_uses_runtime_default_resolvers(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "default_provider: openai\n"
        "default_model: gpt-test\n"
        "providers:\n"
        "  openai:\n"
        "    type: openai-compatible\n"
        "    base_url: https://example.com/v1\n"
        "    default_model: gpt-test\n"
        "    credential_ref: openai\n",
        encoding="utf-8",
    )
    credentials = InMemoryCredentialStore()
    credentials.set("openai", "test-key")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=credentials,
    )

    assert deps.loop.provider_registry is deps.provider_registry
    assert deps.loop.default_provider() == "openai"
    assert deps.loop.default_model() == "gpt-test"


def test_bootstrap_wires_llm_summarizer(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("", encoding="utf-8")
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )

    assert deps.context.summarizer is not None
    assert isinstance(deps.context.summarizer, LLMSummarizer)


def test_bootstrap_wires_hooks_and_mcp_from_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "hooks:\n"
        "  task_start:\n"
        "    - type: command\n"
        "      command: notify.sh\n"
        "mcp:\n"
        "  filesystem:\n"
        "    command: npx\n"
        "    args: ['-y', '@modelcontextprotocol/server-filesystem']\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )

    assert deps.hooks.hooks["task_start"][0]["command"] == "notify.sh"
    assert deps.mcp.servers["filesystem"]["command"] == "npx"
    assert deps.mcp.servers["filesystem"]["args"] == [
        "-y",
        "@modelcontextprotocol/server-filesystem",
    ]


def test_bootstrap_provider_reads_api_key_from_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com\n"
        "    default_model: deepseek-chat\n"
        "    api_key: sk-from-yaml\n",
        encoding="utf-8",
    )
    deps = build_app_dependencies(
        config_path=config_path,
        db_path=tmp_path / "kl.db",
        workspace=str(tmp_path),
        log_path=tmp_path / "audit.jsonl",
        credential_store=InMemoryCredentialStore(),
    )

    provider = deps.provider_registry.get("deepseek")
    assert provider.api_key == "sk-from-yaml"
