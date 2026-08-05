from pydantic import BaseModel, ConfigDict


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    type: str = "openai-compatible"
    base_url: str
    default_model: str
    credential_ref: str | None = None


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderConfig] = {}
    default_provider: str = "mock"
    default_model: str = ""  # 全局默认模型；空则用各 provider 自身的 default_model
