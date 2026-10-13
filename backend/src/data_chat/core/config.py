from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        str_strip_whitespace=True,
    )

    app_environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"] = "INFO"
    openai_api_key: SecretStr | None = None
    openai_model: str | None = Field(default=None, min_length=1)
    openai_request_timeout_seconds: int = Field(default=30, gt=0, le=120)
    sql_server_odbc_connection_string: SecretStr | None = None
    sql_server_connection_timeout_seconds: int = Field(default=10, gt=0, le=120)
    sql_server_query_timeout_seconds: int = Field(default=30, gt=0, le=300)
