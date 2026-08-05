# 运行时全局模型切换设计

日期：2026-08-05
状态：已批准

## 背景与目标

当前 KL Code 的 LLM provider/模型在**服务端启动时**从 `.kl/config.yaml` 一次性加载并注入 AgentLoop（`config.default_provider` 选出唯一 provider）。运行时没有切换模型的能力，必须编辑配置后重启。

目标：让用户**在运行中**切换全局默认模型（provider + 可选模型名），切换后**所有会话（含已存在会话）统一受影响**，无需重启服务端。交互入口：TUI 斜杠命令 `/model` + CLI 命令 `kl config model …`。

范围决策（用户已确认）：
- 切换粒度为**仅全局**（不做会话级覆盖）。
- 交互入口为 **TUI 斜杠命令 + CLI 命令**。

## 方案

采用方案 A：**运行时动态解析 provider**。AgentLoop 持有 `ProviderRegistry` 与指向可变 `AppConfig` 的解析器，每次 `run()` 时按当前全局默认解析 provider/model。切换 API 直接改内存配置并持久化到 `config.yaml`。

### 关键语义

现有 session 的 `model` 字段均为默认值 `"mock-model"` 占位符（系统中没有设置该字段的路径）。AgentLoop 中 `"mock-model"` 会回退到全局默认模型，因此**切换后所有会话自然统一受影响**，无需改动 session。

## 架构与数据流

```
用户（CLI / TUI）
   │  POST /api/v1/config/model  {provider, model?}
   ▼
routes.py ── 校验 provider 存在
   ├─ 更新 deps.config.default_provider / default_model（内存，可变）
   └─ 写回 config.yaml（_persist_config，重启后仍生效）
   ▼
后续 run_task → _execute_task → deps.loop.run()
   └─ loop 从 provider_registry 按 config.default_provider 取 provider
      └─ model = session.model(非mock-model) → 全局 default_model → provider.model
```

## 组件改动

### 服务端

**1. `server/kl_server/config/config.py` — AppConfig 新增字段**

```python
class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    providers: dict[str, ProviderConfig] = {}
    default_provider: str = "mock"
    default_model: str = ""   # 新增：全局默认模型，空则用 provider 自身的 default_model
```

### 2. `server/kl_server/core/agent_loop.py` — AgentLoop 动态解析

新增可选构造参数（保持 `provider=` 构造向后兼容，现有测试不改）：

```python
provider_registry: ProviderRegistry | None = None
default_provider: Callable[[], str] | None = None   # 返回当前默认 provider 名
default_model: Callable[[], str] | None = None      # 返回当前全局默认模型（可空）
```

`run()` 中：

```python
provider = self.provider
if self.provider_registry is not None and self.default_provider is not None:
    try:
        provider = self.provider_registry.get(self.default_provider())
    except KeyError:
        pass  # 回退 self.provider
...
model = session.model
if not model or model == "mock-model":
    global_model = (self.default_model() if self.default_model is not None else "") or ""
    model = global_model or (getattr(provider, "model", None) or model)
```

### 3. `server/kl_server/bootstrap.py` — 注入 registry 与解析器

构造 AgentLoop 时传：

```python
provider_registry=providers,
default_provider=lambda: config.default_provider,
default_model=lambda: config.default_model,
```

（原 `provider = providers.get(config.default_provider)` 的预解析可保留作为兜底，也可移除——loop 运行时会解析。）

### 4. `server/kl_server/api/routes.py` — 模型配置 API

新增 payload：

```python
class ModelConfigPayload(BaseModel):
    provider: str
    model: str = ""   # 空表示使用该 provider 的 default_model
```

新增路由：

- `GET /api/v1/config/model`
  - 返回 `{"provider": config.default_provider, "model": <当前生效模型>, "available": [{provider, model, base_url}]}`
  - `available` 由 `config.providers` 各 provider 的 `default_model` + `mock` 推导；`model` 为全局 `default_model` 或当前 provider 的 `default_model`（按 AgentLoop 优先级算）。
- `POST /api/v1/config/model`
  - 校验 `provider` 为 `"mock"` 或 `config.providers` 中已注册；否则 `404 {"detail": "provider not found"}`。
  - 更新 `deps.config.default_provider = provider`；若 `model` 非空则 `deps.config.default_model = model`，否则清空 `default_model`（回退 provider 默认）。
  - 调用 `_persist_config(deps)` 写回 config.yaml。
  - 返回新状态（同 GET 结构）。

调整现有端点：

- `GET /api/v1/models`：从硬编码 `[{"name": "mock-model"}]` 改为返回 `available` 列表（每项含 provider 名与模型名）。
- `POST /api/v1/config/check`：`providers` 从硬编码 `["mock"]` 改为 `["mock"] + list(deps.config.providers)`（无 deps 时保持 `["mock"]`）。

### CLI

**5. `cli/src/api/client.ts`** 新增方法：

```ts
getModelConfig(): Promise<{provider: string; model: string; available: ...}>
setModelConfig(payload: {provider: string; model?: string}): Promise<...>
listModels(): Promise<...>   // GET /models
```

**6. `cli/src/commands/config.ts`** 新增 `model` area：

- `kl config model set <provider> [model]`
- `kl config model show`
- `kl config model list`
- 复用现有 `ConfigCommand.run` 的 `area === 'model'` 分支。

### TUI

**7. `cli/src/tui/app.tsx`** 新增 `/model` 斜杠命令：

- SLASH_COMMANDS 增加 `{ name: '/model', desc: '查看/切换模型' }`。
- `runSlashCommand` 处理：
  - `/model` → 调 `getModelConfig()`，`pushMessage` 显示当前 provider/model 与可用列表。
  - `/model <provider>` → `setModelConfig({provider})`。
  - `/model <provider> <model>` → `setModelConfig({provider, model})`。
- 结果以 info 消息展示，错误以 error 消息展示。

## 错误处理

- 切换不存在的 provider：API 返回 404，CLI/TUI 展示 `provider not found`。
- registry 取 provider 抛 KeyError（配置异常）：loop 回退 `self.provider`（bootstrap 兜底为 mock），不阻断任务执行。
- 配置持久化失败：`_persist_config` 抛异常时切换失败，API 返回 500（沿用现有 provider add 行为）。

## 测试

### 服务端（pytest）

- `test_agent_loop.py` 新增：构造 AgentLoop 传 registry + resolver，验证 run 时按当前默认 provider 解析；切换 resolver 返回值后再次 run 用新 provider；KeyError 回退。
- `test_routes.py` 新增：`GET/POST /api/v1/config/model` 成功与 404；持久化后 config.yaml 内容包含 `default_provider`/`default_model`；`/models` 返回实际列表。
- `test_bootstrap.py`：确认 loop 携带 registry 与解析器（可选）。

### CLI（vitest）

- `client.test.ts`：`getModelConfig`/`setModelConfig` 请求路径与 body。
- `commands.test.ts`（或 config 相关）：`kl config model set/show/list` 输出与请求。
- `init.test.ts`：若 `config/check` 响应断言 `providers: ['mock']` 保持不变（无 deps 场景），确认不受影响。

### 回归

- 现有 CLI 53 个测试与 server pytest 全量通过；AgentLoop 改动向后兼容（新参数可选）。
- 手动链路：`server start` → `kl config model show`（mock）→ `kl config model set <provider> [model]` → `show` 反映新值 → 重启后配置仍在（config.yaml 持久化）。

## 不在范围内

- 会话级模型覆盖（用户明确选择仅全局）。
- 从 provider 拉取真实模型列表（openai-compatible 的 `/models` 探测）；可用模型以各 provider 配置的 `default_model` 为准，允许任意模型名由 provider 端校验。
- TUI 交互式模型选择列表（当前为参数式 `/model <provider> [model]`）。
