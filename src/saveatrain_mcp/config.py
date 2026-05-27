import os

from pydantic import HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def __init__(self, **data):
        super().__init__(_env_file=os.getenv("SAT_MCP_ENV_FILE", ".env"), **data)

    sat_api_base_url: HttpUrl
    sat_agent_email: str
    sat_agent_token: SecretStr
    sat_forwarded_for: str

    mongo_uri: str
    mongo_db: str = "sat"

    host: str = "127.0.0.1"
    port: int = 8000
