from pydantic import BaseModel, ConfigDict


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    type: str = "openai-compatible"
    base_url: str
    default_model: str
    credential_ref: str | None = None
    # 直接写在配置文件里的 API key（本地工具场景，用户自行管理；.kl/ 已 gitignore）
    api_key: str | None = None
    # 当前模型的最大上下文 token 数；未配置时默认 20k
    max_context: int = 20000
    # 可选的多模型列表；为空时仍使用 default_model
    models: list[str] = []


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderConfig] = {}
    default_provider: str = "mock"
    default_model: str = ""  # 全局默认模型；空则用各 provider 自身的 default_model
    hooks: dict[str, list[dict]] = {}  # 生命周期 hook 配置（command/http），key 为事件名
    mcp: dict[str, dict] = {}  # MCP server 配置，key 为 server 名
