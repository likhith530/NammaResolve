from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-backed application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    agora_app_id: str = ""
    agora_app_certificate: SecretStr = SecretStr("")
    agora_area: str = "US"
    agora_llm_model: str = "gpt-4o-mini"
    agora_stt_model: str = "nova-3"

    murf_api_key: SecretStr = SecretStr("")
    murf_voice_id: str = "Matthew"
    murf_locale: str = "en-US"
    murf_base_url: str = "wss://global.api.murf.ai/v1/speech/stream-input"

    public_base_url: str = ""
    tool_api_key: SecretStr = SecretStr("replace-with-a-long-random-secret")
    database_path: str = "./data/nammaresolve.db"

    @property
    def database_file(self) -> Path:
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def tool_secret(self) -> str:
        return self.tool_api_key.get_secret_value()

    @property
    def murf_secret(self) -> str:
        return self.murf_api_key.get_secret_value()

    @property
    def agora_certificate(self) -> str:
        return self.agora_app_certificate.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
