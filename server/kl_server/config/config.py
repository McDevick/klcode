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
