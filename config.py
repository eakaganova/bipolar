import json
import logging
import os
from functools import lru_cache
from typing import Any

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    public_base_url: str = Field(..., alias="PUBLIC_BASE_URL")
    webhook_path: str = Field(default="/webhook", alias="WEBHOOK_PATH")
    port: int = Field(default=10000, alias="PORT")

    google_sheet_id: str = Field(..., alias="GOOGLE_SHEET_ID")
    google_worksheet_name: str = Field(default="entries", alias="GOOGLE_WORKSHEET_NAME")
    google_service_account_json: str | None = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_JSON")
    google_service_account_file: str | None = Field(default=None, alias="GOOGLE_SERVICE_ACCOUNT_FILE")

    openai_transcription_model: str = Field(default="whisper-1", alias="OPENAI_TRANSCRIPTION_MODEL")
    openai_analysis_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_ANALYSIS_MODEL")
    openai_reflection_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_REFLECTION_MODEL")

    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/{self.webhook_path.strip('/')}"

    def google_credentials(self) -> dict[str, Any] | str:
        if self.google_service_account_json:
            return json.loads(self.google_service_account_json)
        if self.google_service_account_file:
            return self.google_service_account_file
        raise ValueError("Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_FILE")


@lru_cache
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing = ", ".join(error["loc"][0] for error in exc.errors())
        raise RuntimeError(f"Missing or invalid environment variables: {missing}") from exc


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.INFO)
