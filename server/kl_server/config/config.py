from pydantic import BaseModel, ConfigDict


class ProviderConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: str
    base_url: str
    default_model: str
    credential_ref: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    providers: dict[str, ProviderConfig] = {}
    default_provider: str = "mock"
