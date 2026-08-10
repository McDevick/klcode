from pydantic import BaseModel, ConfigDict, field_validator


class SandboxConfig(BaseModel):
    allow: list[str] = []
    deny: list[str] = ["rm", "docker"]
    deny_all: bool = False
    timeout: float | None = None
    max_cpu_seconds: float | None = None
    max_memory_mb: int | None = None


class GuardrailConfig(BaseModel):
    approval_timeout_seconds: float = 300.0

    @field_validator("approval_timeout_seconds")
    @classmethod
    def _validate_approval_timeout(cls, value: float) -> float:
        if value < 30 or value > 1800:
            raise ValueError("approval_timeout_seconds must be between 30 and 1800")
        return value


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


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_outputs_dir: str | None = None
    tool_outputs_retention_days: int | None = None
    tool_outputs_max_mb: int | None = None

    @field_validator("tool_outputs_retention_days", "tool_outputs_max_mb")
    @classmethod
    def _validate_positive_limits(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("tool_outputs retention/max_mb must be positive")
        return value


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderConfig] = {}
    default_provider: str = "mock"
    default_model: str = ""  # 全局默认模型；空则用各 provider 自身的 default_model
    hooks: dict[str, list[dict]] = {}  # 生命周期 hook 配置（command/http），key 为事件名
    mcp: dict[str, dict] = {}  # MCP server 配置，key 为 server 名
    storage: StorageConfig = StorageConfig()
    sandbox: SandboxConfig = SandboxConfig()
    guardrail: GuardrailConfig = GuardrailConfig()
