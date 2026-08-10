# 运行时全局模型切换 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户在运行中切换全局默认 LLM provider/模型（TUI `/model` + CLI `kl config model …`），切换后所有会话统一生效且持久化到 `config.yaml`，无需重启服务端。

**Architecture:** AgentLoop 从启动时绑死单个 provider 改为持有 `ProviderRegistry` + 指向可变 `AppConfig` 的解析器，每次 `run()` 按 `config.default_provider` 解析 provider、按 `config.default_model`（空则回退 provider 的 default_model）选模型。切换通过新 API `GET/POST /api/v1/config/model` 修改内存配置并写回 config.yaml。

**Tech Stack:** Python FastAPI + pydantic（服务端）、TypeScript + Ink/Commander（CLI/TUI）、vitest + pytest（测试）。

**Spec:** `docs/superpowers/specs/2026-08-05-runtime-model-switch-design.md`

## Global Constraints

- 服务端测试必须用项目 venv 的 python 运行：`E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/<file> -q`（或激活 venv 后 `python -m pytest …`）。
- CLI 测试：`cd cli && npm test`（或 `npx vitest run test/<file>.test.ts`）。
- 保持现有 `AgentLoop(provider=…)` 构造签名向后兼容——新增参数全部可选，现有 53 个 CLI 测试与 server pytest 不得回归。
- `AppConfig` 是 `extra="forbid"`——新增字段必须同时加在 pydantic 模型上，否则已含该 key 的 config.yaml 会加载失败。
- 模型切换语义：`session.model` 仍保持现有逻辑（非 `"mock-model"` 时优先），但系统中无设置它的路径，实际所有 session 为 `"mock-model"` 会回退到全局默认模型，因此**已存在会话统一受影响**。
- 不在范围内：会话级模型覆盖、真实 provider 的模型列表探测、TUI 交互式选择列表。

---

### Task 1: AppConfig 新增 `default_model` 字段

**Files:**
- Modify: `server/kl_server/config/config.py`
- Test: `server/tests/test_config.py`（新建）

**Interfaces:**
- Produces: `AppConfig` 新增字段 `default_model: str = ""`（全局默认模型，空表示用 provider 自身的 `default_model`）。

- [ ] **Step 1: 写失败测试**

新建 `server/tests/test_config.py`：

```python
from pathlib import Path

from kl_server.config.config import AppConfig
from kl_server.config.loader import load_app_config


def test_app_config_default_model_defaults_to_empty():
    config = AppConfig()

    assert config.default_provider == "mock"
    assert config.default_model == ""


def test_app_config_loads_default_model_from_yaml(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "default_provider: deepseek\n"
        "default_model: deepseek-chat\n"
        "providers:\n"
        "  deepseek:\n"
        "    type: openai-compatible\n"
        "    base_url: https://api.deepseek.com/v1\n"
        "    default_model: deepseek-chat\n",
        encoding="utf-8",
    )

    config = load_app_config(path)

    assert config.default_provider == "deepseek"
    assert config.default_model == "deepseek-chat"
```

- [ ] **Step 2: 运行测试确认失败**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_config.py -q`
预期: 失败——`AppConfig` 报 `default_model` 不是合法字段（extra="forbid" 拒绝，或字段缺失导致断言失败）。

- [ ] **Step 3: 最小实现**

在 `server/kl_server/config/config.py` 的 `AppConfig` 加字段：

```python
class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderConfig] = {}
    default_provider: str = "mock"
    default_model: str = ""  # 全局默认模型；空则用各 provider 自身的 default_model
```

- [ ] **Step 4: 运行测试确认通过**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_config.py -q`
预期: PASS（2 项）。

- [ ] **Step 5: 提交**

```bash
git add server/kl_server/config/config.py server/tests/test_config.py
git commit -m "feat: add global default_model to AppConfig"
```

---

### Task 2: AgentLoop 运行时动态解析 provider/model

**Files:**
- Modify: `server/kl_server/core/agent_loop.py`
- Test: `server/tests/test_agent_loop.py`

**Interfaces:**
- Consumes: `ProviderRegistry`（`kl_server/providers/registry.py`，`get(name)` 抛 `KeyError`）、`MockProvider`（无 `model` 属性）。
- Produces: `AgentLoop` 新增可选构造参数 `provider_registry: ProviderRegistry | None = None`、`default_provider: Callable[[], str] | None = None`、`default_model: Callable[[], str] | None = None`；`run()` 中 provider 解析逻辑。

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_agent_loop.py` 末尾追加（保持现有 imports，另加 `from kl_server.providers.registry import ProviderRegistry`）：

```python
@pytest.mark.asyncio
async def test_loop_resolves_provider_from_registry_by_current_default():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider_a = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    provider_b = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    providers.register("a", provider_a)
    providers.register("b", provider_b)
    current = {"name": "a"}
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),  # 兜底，不应被使用
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        provider_registry=providers,
        default_provider=lambda: current["name"],
        default_model=lambda: "",
    )

    await loop.run(Session(id="s1", workspace="."), "finish task")

    assert len(provider_a.calls) == 2
    assert len(provider_b.calls) == 0

    current["name"] = "b"
    await loop.run(Session(id="s2", workspace="."), "finish task")

    assert len(provider_a.calls) == 2
    assert len(provider_b.calls) == 2


@pytest.mark.asyncio
async def test_loop_uses_global_default_model_when_session_is_mock_placeholder():
    registry = ToolRegistry()
    registry.register(FinalTool())
    providers = ProviderRegistry()
    provider = MockProvider(responses=["DONE"])
    provider.model = "provider-model"
    providers.register("p", provider)
    loop = AgentLoop(
        provider=MockProvider(responses=["DONE"]),
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=2),
        provider_registry=providers,
        default_provider=lambda: "p",
        default_model=lambda: "global-model",
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert provider.calls[0].model == "global-model"


@pytest.mark.asyncio
async def test_loop_falls_back_to_injected_provider_when_registry_misses():
    registry = ToolRegistry()
    registry.register(FinalTool())
    fallback = MockProvider(responses=['{"tool":"final","args":{}}', "DONE"])
    loop = AgentLoop(
        provider=fallback,
        tools=ToolExecutor(registry),
        settings=LoopSettings(max_iterations=3),
        provider_registry=ProviderRegistry(),  # 默认只含 mock，无 "missing"
        default_provider=lambda: "missing",
        default_model=lambda: "",
    )

    await loop.run(Session(id="s1", workspace="."), "task")

    assert len(fallback.calls) == 2
```

- [ ] **Step 2: 运行测试确认失败**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_agent_loop.py -q`
预期: 失败——`TypeError: __init__() got an unexpected keyword argument 'provider_registry'`。

- [ ] **Step 3: 最小实现**

在 `server/kl_server/core/agent_loop.py` 顶部加 import：

```python
from collections.abc import Callable

from kl_server.providers.registry import ProviderRegistry
```

修改 `AgentLoop.__init__` 与 `run()`：

```python
class AgentLoop:
    def __init__(
        self,
        provider,
        tools: ToolExecutor,
        settings: LoopSettings,
        logger=None,
        on_approval=None,
        context=None,
        memory=None,
        hooks=None,
        skills=None,
        provider_registry: ProviderRegistry | None = None,
        default_provider: Callable[[], str] | None = None,
        default_model: Callable[[], str] | None = None,
    ):
        self.provider = provider
        self.provider_registry = provider_registry
        self.default_provider = default_provider
        self.default_model = default_model
        self.tools = tools
        self.settings = settings
        self.logger = logger
        self.on_approval = on_approval
        self.context = context
        self.memory = memory
        self.hooks = hooks
        self.skills = skills
```

在 `run()` 中，将 `for iteration ...` 循环之前的 model 解析段（原第 99-106 行）替换为：

```python
                provider = self.provider
                if self.provider_registry is not None and self.default_provider is not None:
                    try:
                        provider = self.provider_registry.get(self.default_provider())
                    except KeyError:
                        pass  # 回退 self.provider
                # Sessions default to the mock model name; fall back to the
                # global default model, then to the provider's own default.
                model = session.model
                if not model or model == "mock-model":
                    global_model = (self.default_model() if self.default_model is not None else "") or ""
                    model = global_model or (getattr(provider, "model", None) or model)
                response = await provider.complete(
                    ProviderRequest(messages=request_messages, model=model)
                )
```

注意：`provider` 现在是 `run()` 的局部变量（不再用 `self.provider` 调用 `complete`），`getattr(provider, "model", None)` 也改用局部变量。

- [ ] **Step 4: 运行测试确认通过**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_agent_loop.py -q`
预期: PASS（原 12 项 + 新 3 项）。

- [ ] **Step 5: 提交**

```bash
git add server/kl_server/core/agent_loop.py server/tests/test_agent_loop.py
git commit -m "feat: agent loop resolves provider at runtime from registry"
```

---

### Task 3: bootstrap 注入 registry 与解析器

**Files:**
- Modify: `server/kl_server/bootstrap.py`
- Test: `server/tests/test_bootstrap.py`

**Interfaces:**
- Consumes: Task 2 的 `AgentLoop` 新参数。
- Produces: `AppDependencies.loop` 携带 `provider_registry`（即 `deps.provider_registry`）、`default_provider()`、`default_model()`。

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_bootstrap.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_bootstrap.py::test_bootstrap_loop_uses_runtime_default_resolvers -q`
预期: 失败——`AttributeError: 'AgentLoop' object has no attribute 'provider_registry'`。

- [ ] **Step 3: 最小实现**

在 `server/kl_server/bootstrap.py` 构造 AgentLoop 处（约第 92-101 行）追加参数：

```python
    loop = AgentLoop(
        provider=provider,
        tools=executor,
        settings=LoopSettings(),
        logger=logger,
        context=context,
        memory=memory,
        hooks=hooks,
        skills=skills,
        provider_registry=providers,
        default_provider=lambda: config.default_provider,
        default_model=lambda: config.default_model,
    )
```

（原 `provider = providers.get(config.default_provider)` + KeyError 兜底逻辑保留，作为解析失败的兜底 provider。）

- [ ] **Step 4: 运行测试确认通过**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_bootstrap.py -q`
预期: PASS（原 3 项 + 新 1 项）。

- [ ] **Step 5: 提交**

```bash
git add server/kl_server/bootstrap.py server/tests/test_bootstrap.py
git commit -m "feat: wire provider registry and default resolvers into agent loop"
```

---

### Task 4: 模型配置 API

**Files:**
- Modify: `server/kl_server/api/routes.py`
- Test: `server/tests/test_routes.py`

**Interfaces:**
- Consumes: `AppConfig`（含 `default_model`）、`_persist_config(deps)`。
- Produces:
  - `GET /api/v1/config/model` → `{"provider": str, "model": str, "available": [{provider, model, base_url}]}`
  - `POST /api/v1/config/model` body `{provider: str, model?: str}` → 同 GET 结构；provider 不存在返回 404 `{"detail": "provider not found"}`。
  - `GET /api/v1/models` → `[{provider, model, base_url}]`
  - `POST /api/v1/config/check` 的 `providers` 含实际配置的 provider 名。

- [ ] **Step 1: 更新现有 `/models` 测试（结构变化）**

将 `server/tests/test_routes.py` 的 `test_models_route_includes_mock_model` 改为断言新结构：

```python
def test_models_route_includes_mock_model():
    client = make_client()

    response = client.get("/api/v1/models")

    assert response.status_code == 200
    assert any(item["model"] == "mock-model" for item in response.json())
```

- [ ] **Step 2: 写失败测试**

在 `server/tests/test_routes.py` 末尾追加（`yaml` 与 `build_app_dependencies`、`InMemoryCredentialStore`、`create_app`、`TestClient` 已在文件顶部 import）：

```python
def test_config_model_get_returns_current_default(tmp_path):
    client = make_deps_client(tmp_path)

    response = client.get("/api/v1/config/model")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["model"] == "mock-model"
    assert {"provider": "mock", "model": "mock-model", "base_url": ""} in body["available"]


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
```

- [ ] **Step 3: 运行测试确认失败**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_routes.py -q`
预期: 失败——`/api/v1/config/model` 返回 404/405，`/models` 结构断言失败，config/check 不含 `deepseek`。

- [ ] **Step 4: 最小实现**

在 `server/kl_server/api/routes.py`：
1. import 处加 `from kl_server.config.config import AppConfig, ProviderConfig`（`ProviderConfig` 已有）。
2. 加 payload 与 helper（放在 `class KeyPayload` 之后、`build_router` 之前）：

```python
class ModelConfigPayload(BaseModel):
    provider: str
    model: str = ""


def _model_available(config: AppConfig) -> list[dict]:
    available = [{"provider": "mock", "model": "mock-model", "base_url": ""}]
    for name, provider_config in config.providers.items():
        available.append(
            {
                "provider": name,
                "model": provider_config.default_model,
                "base_url": provider_config.base_url,
            }
        )
    return available


def _model_state(config: AppConfig) -> dict:
    available = _model_available(config)
    provider = config.default_provider
    model = config.default_model
    if not model:
        if provider == "mock":
            model = "mock-model"
        else:
            provider_config = config.providers.get(provider)
            model = provider_config.default_model if provider_config else ""
    return {"provider": provider, "model": model, "available": available}
```

3. 修改 `config/check`（原 301-310 行）为：

```python
    @router.post("/config/check")
    def config_check(request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is not None:
            providers = ["mock"] + list(deps.config.providers.keys())
            if getattr(deps, "config_error", None):
                return {
                    "status": "degraded",
                    "providers": providers,
                    "error": deps.config_error,
                }
            return {"status": "ok", "providers": providers}
        return {"status": "ok", "providers": ["mock"]}
```

4. 新增路由（放在 `config/check` 之后）：

```python
    @router.get("/config/model")
    def get_model_config(request: Request):
        deps = getattr(request.app.state, "deps", None)
        return _model_state(deps.config if deps is not None else AppConfig())

    @router.post("/config/model")
    def set_model_config(payload: ModelConfigPayload, request: Request):
        deps = getattr(request.app.state, "deps", None)
        if deps is None:
            raise HTTPException(status_code=501, detail="requires a configured server")
        if payload.provider != "mock" and payload.provider not in deps.config.providers:
            raise HTTPException(status_code=404, detail="provider not found")
        deps.config.default_provider = payload.provider
        deps.config.default_model = payload.model
        _persist_config(deps)
        return _model_state(deps.config)
```

5. 替换 `/models`（原 354-356 行）为：

```python
    @router.get("/models")
    def list_models(request: Request):
        deps = getattr(request.app.state, "deps", None)
        return _model_available(deps.config if deps is not None else AppConfig())
```

- [ ] **Step 5: 运行测试确认通过**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests/test_routes.py -q`
预期: PASS（原所有 + 新 5 项；其中 `test_config_check_reports_mock_provider` 用无 deps 场景不受影响）。

- [ ] **Step 6: 提交**

```bash
git add server/kl_server/api/routes.py server/tests/test_routes.py
git commit -m "feat: model config api with runtime provider switch and persistence"
```

---

### Task 5: CLI client 新增模型配置方法

**Files:**
- Modify: `cli/src/api/client.ts`
- Test: `cli/test/client.test.ts`

**Interfaces:**
- Produces:
  - `interface ModelConfig { provider: string; model: string; available: Array<{ provider: string; model: string; base_url: string }> }`
  - `ApiClient.getModelConfig(): Promise<ModelConfig>`
  - `ApiClient.setModelConfig(payload: { provider: string; model?: string }): Promise<ModelConfig>`
  - `ApiClient.listModels(): Promise<Array<{ provider: string; model: string; base_url: string }>>`

- [ ] **Step 1: 写失败测试**

在 `cli/test/client.test.ts` 末尾追加：

```ts
test('client gets model config', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      provider: 'mock',
      model: 'mock-model',
      available: [{ provider: 'mock', model: 'mock-model', base_url: '' }],
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    const result = await client.getModelConfig();

    expect(result.provider).toBe('mock');
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('client sets model config with provider and model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ provider: 'deepseek', model: 'deepseek-chat', available: [] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    await client.setModelConfig({ provider: 'deepseek', model: 'deepseek-chat' });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ provider: 'deepseek', model: 'deepseek-chat' });
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({ method: 'POST' }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('client lists models', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [{ provider: 'mock', model: 'mock-model', base_url: '' }],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const client = new ApiClient({ baseUrl: 'http://127.0.0.1:8700' });
    const result = await client.listModels();

    expect(result[0]).toMatchObject({ provider: 'mock', model: 'mock-model' });
  } finally {
    vi.unstubAllGlobals();
  }
});
```

- [ ] **Step 2: 运行测试确认失败**

运行: `cd cli && npx vitest run test/client.test.ts`
预期: 失败——`client.getModelConfig is not a function`。

- [ ] **Step 3: 最小实现**

在 `cli/src/api/client.ts` 加接口与方法（`TaskResult` 接口附近加接口，`health()` 方法后加方法）：

```ts
export interface ModelConfig {
  provider: string;
  model: string;
  available: Array<{ provider: string; model: string; base_url: string }>;
}
```

```ts
  getModelConfig(): Promise<ModelConfig> {
    return this.request('/api/v1/config/model');
  }

  setModelConfig(payload: { provider: string; model?: string }): Promise<ModelConfig> {
    return this.request('/api/v1/config/model', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ provider: payload.provider, model: payload.model ?? '' }),
    });
  }

  listModels(): Promise<Array<{ provider: string; model: string; base_url: string }>> {
    return this.request('/api/v1/models');
  }
```

- [ ] **Step 4: 运行测试确认通过**

运行: `cd cli && npx vitest run test/client.test.ts`
预期: PASS（原 6 项 + 新 3 项）。

- [ ] **Step 5: 提交**

```bash
git add cli/src/api/client.ts cli/test/client.test.ts
git commit -m "feat: cli client model config methods"
```

---

### Task 6: CLI `config model` 子命令

**Files:**
- Modify: `cli/src/commands/config.ts`
- Test: `cli/test/commands.test.ts`

**Interfaces:**
- Consumes: Task 5 的 `ApiClient.getModelConfig` / `setModelConfig` / `listModels`。
- Produces: `kl config model set <provider> [model]`、`kl config model show`、`kl config model list`。

- [ ] **Step 1: 写失败测试**

在 `cli/test/commands.test.ts` 末尾追加：

```ts
test('config model show returns current model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      provider: 'mock',
      model: 'mock-model',
      available: [{ provider: 'mock', model: 'mock-model', base_url: '' }],
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['model', 'show']);

    expect(result).toContain('mock-model');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/config/model`,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config model set posts provider and model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ provider: 'deepseek', model: 'deepseek-chat', available: [] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['model', 'set', 'deepseek', 'deepseek-chat']);

    expect(result).toContain('deepseek');
    expect(fetchMock).toHaveBeenCalledWith(
      `${DEFAULT_BASE_URL}/api/v1/config/model`,
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ provider: 'deepseek', model: 'deepseek-chat' }),
      }),
    );
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config model set without model posts empty model', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ provider: 'deepseek', model: 'deepseek-chat', available: [] }),
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    await ConfigCommand.run(['model', 'set', 'deepseek']);

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ provider: 'deepseek', model: '' });
  } finally {
    vi.unstubAllGlobals();
  }
});

test('config model list shows available providers', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => [
      { provider: 'mock', model: 'mock-model', base_url: '' },
      { provider: 'deepseek', model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' },
    ],
  });
  vi.stubGlobal('fetch', fetchMock);
  try {
    const result = await ConfigCommand.run(['model', 'list']);

    expect(result).toContain('mock: mock-model');
    expect(result).toContain('deepseek: deepseek-chat');
  } finally {
    vi.unstubAllGlobals();
  }
});
```

- [ ] **Step 2: 运行测试确认失败**

运行: `cd cli && npx vitest run test/commands.test.ts`
预期: 失败——`runModel` 未定义 / `config model` 落入默认分支返回 usage。

- [ ] **Step 3: 最小实现**

在 `cli/src/commands/config.ts` 加 `runModel` 并在 `run()` 中加分支：

```ts
async function runModel(subcommand: string | undefined, rest: string[]): Promise<string> {
  const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });

  switch (subcommand) {
    case 'set': {
      const [provider, model] = rest;
      if (!provider) {
        return 'usage: kl config model set <provider> [model]';
      }
      const state = await client.setModelConfig(model ? { provider, model } : { provider });
      return `model: ${state.provider} / ${state.model}`;
    }
    case 'show': {
      const state = await client.getModelConfig();
      return `provider: ${state.provider}\nmodel: ${state.model}`;
    }
    case 'list': {
      const available = await client.listModels();
      return available.map((item) => `${item.provider}: ${item.model}`).join('\n');
    }
    default:
      return 'usage: kl config model set|show|list';
  }
}
```

`run()` 中在 `if (area === 'key')` 分支后加：

```ts
    if (area === 'model') {
      return runModel(subcommand, rest);
    }
```

- [ ] **Step 4: 运行测试确认通过**

运行: `cd cli && npx vitest run test/commands.test.ts`
预期: PASS（原所有 + 新 4 项）。

- [ ] **Step 5: 提交**

```bash
git add cli/src/commands/config.ts cli/test/commands.test.ts
git commit -m "feat: kl config model set/show/list subcommands"
```

---

### Task 7: TUI `/model` 斜杠命令

**Files:**
- Modify: `cli/src/tui/app.tsx`
- Test: `cli/test/tui.test.tsx`

**Interfaces:**
- Consumes: Task 5 的 `ApiClient.getModelConfig` / `setModelConfig`。
- Produces: TUI 内 `/model` 命令——无参数显示当前+可用；`/model <provider> [model]` 切换。

- [ ] **Step 1: 写失败测试**

在 `cli/test/tui.test.tsx` 末尾追加：

```ts
test('app /model shows current and available models', async () => {
  // 第 1 次 fetch：App 初始化创建 session；第 2 次 fetch：/model 读取模型配置
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(sessionResponse)
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        provider: 'mock',
        model: 'mock-model',
        available: [{ provider: 'mock', model: 'mock-model', base_url: '' }],
      }),
    });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/model');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('当前: mock / mock-model'));
    expect(lastFrame()).toContain('当前: mock / mock-model');
    expect(lastFrame()).toContain('mock: mock-model');
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});

test('app /model <provider> switches model via api', async () => {
  // 第 1 次 fetch：创建 session；第 2 次 fetch：/model 切换（POST）
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(sessionResponse)
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        provider: 'deepseek',
        model: 'deepseek-chat',
        available: [{ provider: 'deepseek', model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' }],
      }),
    });
  vi.stubGlobal('fetch', fetchMock);
  const restore = stubWebSocket();
  const { stdin, lastFrame, unmount } = render(<App />);
  try {
    await waitFor(() => (lastFrame() ?? '').includes('会话 s1 已就绪'));
    stdin.write('/model deepseek');
    stdin.write('\r');
    await waitFor(() => (lastFrame() ?? '').includes('模型已切换: deepseek / deepseek-chat'));
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8700/api/v1/config/model',
      expect.objectContaining({ method: 'POST', body: expect.stringContaining('"provider":"deepseek"') }),
    );
  } finally {
    unmount();
    vi.unstubAllGlobals();
    restore();
  }
});
```

> 注意：`/model` 因以 `/` 开头会触发斜杠菜单。为确保输入完整命令直接执行（而非被菜单补全），`submitTask` 中已有"输入完整命令直接执行"逻辑（`filteredCommands.find(name === inputValue)`），`/model` 与 `/model deepseek` 会命中精确匹配。若第二个测试在 `/model deepseek` 时被菜单拦截，改用 `stdin.write('/model deepseek\n')` 直接写换行绕过（与现有 `typing a full slash command` 测试一致的处理）。

- [ ] **Step 2: 运行测试确认失败**

运行: `cd cli && npx vitest run test/tui.test.tsx`
预期: 失败——`/model` 未在命令列表中，显示"未知命令"或未命中预期文案。

- [ ] **Step 3: 最小实现**

在 `cli/src/tui/app.tsx`：

1. `SLASH_COMMANDS` 数组加一项（`/status` 项后）：

```ts
  { name: '/model', desc: '查看/切换模型' },
```

2. `runSlashCommand` 中 `if (commandName === '/config')` 分支后加：

```ts
    if (commandName === '/model') {
      const client = new ApiClient({ baseUrl: DEFAULT_BASE_URL });
      if (args.length === 0) {
        client
          .getModelConfig()
          .then((state) => {
            const lines = [
              `当前: ${state.provider} / ${state.model}`,
              '可用:',
              ...state.available.map((item) => `  ${item.provider}: ${item.model}`),
            ];
            pushMessage('agent', lines.join('\n'), 'info');
          })
          .catch((error: unknown) => {
            pushMessage('agent', `模型配置读取失败: ${String(error)}`, 'error');
          });
        return;
      }
      const provider = args[0];
      const model = args[1];
      client
        .setModelConfig(model ? { provider, model } : { provider })
        .then((state) => {
          pushMessage('agent', `模型已切换: ${state.provider} / ${state.model}`, 'done');
        })
        .catch((error: unknown) => {
          pushMessage('agent', `模型切换失败: ${String(error)}`, 'error');
        });
      return;
    }
```

- [ ] **Step 4: 运行测试确认通过**

运行: `cd cli && npx vitest run test/tui.test.tsx`
预期: PASS（原 12 项 + 新 2 项）。

- [ ] **Step 5: 提交**

```bash
git add cli/src/tui/app.tsx cli/test/tui.test.tsx
git commit -m "feat: tui /model slash command"
```

---

### Task 8: 全量回归与端到端验证

**Files:**
- 无新增；验证整个改动。

- [ ] **Step 1: 运行服务端全量测试**

运行: `E:\projects\SimpleCodingAgent\.superpowers\sdd\PLAN\venv\Scripts\python.exe -m pytest server/tests -q`
预期: 全部 PASS。

- [ ] **Step 2: 运行 CLI 全量测试**

运行: `cd cli && npm test`
预期: 全部 PASS（53 项 + 新增）。

- [ ] **Step 3: 手动端到端验证**

```bash
cd e:/projects/SimpleCodingAgent/cli
npx tsx src/main.ts server start
npx tsx src/main.ts config model show        # 期望: provider: mock / model: mock-model
npx tsx src/main.ts config model list        # 期望: 列出 mock 及已配置 provider
npx tsx src/main.ts config model set deepseek deepseek-chat   # 若已配置 deepseek
npx tsx src/main.ts config model show        # 期望: 反映新值
cat ~/.kl/../<workspace>/.kl/config.yaml     # 期望: default_provider/default_model 已持久化
npx tsx src/main.ts server stop
```

> 若 workspace 中未配置 deepseek provider，`config model set` 对未知 provider 应返回 `provider not found`——这本身也是预期的 404 行为验证。

- [ ] **Step 4: 构建并确认 dist 产物可运行**

```bash
cd cli && npm run build
node dist/main.js config model show
```

预期: 正常输出当前模型。

- [ ] **Step 5: 提交（如有零散改动）**

```bash
git status --short   # 确认工作区干净
```
