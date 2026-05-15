import logging
from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    public_base_url: str = Field(..., alias="PUBLIC_BASE_URL")
    webhook_path: str = Field(default="/webhook", alias="WEBHOOK_PATH")
    port: int = Field(default=10000, alias="PORT")

    storage_provider: str = Field(default="github_csv", alias="STORAGE_PROVIDER")
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_repo: str | None = Field(default=None, alias="GITHUB_REPO")
    github_branch: str = Field(default="data", alias="GITHUB_BRANCH")
    github_csv_path: str = Field(default="data/entries.csv", alias="GITHUB_CSV_PATH")
    local_csv_path: str = Field(default="data/entries.csv", alias="LOCAL_CSV_PATH")

    openai_transcription_model: str = Field(default="whisper-1", alias="OPENAI_TRANSCRIPTION_MODEL")
    openai_analysis_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_ANALYSIS_MODEL")
    openai_reflection_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_REFLECTION_MODEL")

    transcription_provider: str = Field(default="openai", alias="TRANSCRIPTION_PROVIDER")
    llm_provider: str = Field(default="openai", alias="LLM_PROVIDER")
    yandex_cloud_folder: str | None = Field(default=None, alias="YANDEX_CLOUD_FOLDER")
    yandex_cloud_api_key: str | None = Field(default=None, alias="YANDEX_CLOUD_API_KEY")
    yandex_cloud_model: str = Field(default="gpt-oss-120b/latest", alias="YANDEX_CLOUD_MODEL")
    yandex_cloud_base_url: str = Field(default="https://ai.api.cloud.yandex.net/v1", alias="YANDEX_CLOUD_BASE_URL")
    yandex_speech_model: str = Field(default="speech-realtime-250923/latest", alias="YANDEX_SPEECH_MODEL")
    yandex_realtime_wss_url: str = Field(default="wss://llm.api.cloud.yandex.net/v1/realtime", alias="YANDEX_REALTIME_WSS_URL")
    yandex_speech_input_rate: int = Field(default=44100, alias="YANDEX_SPEECH_INPUT_RATE")
    yandex_speech_language: str = Field(default="ru-RU", alias="YANDEX_SPEECH_LANGUAGE")

    request_timeout_seconds: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS")
    max_retries: int = Field(default=3, alias="MAX_RETRIES")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @property
    def webhook_url(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/{self.webhook_path.strip('/')}"

    @property
    def yandex_model_uri(self) -> str:
        if not self.yandex_cloud_folder:
            raise ValueError("Set YANDEX_CLOUD_FOLDER")
        return f"gpt://{self.yandex_cloud_folder}/{self.yandex_cloud_model}"

    @property
    def yandex_speech_model_uri(self) -> str:
        if not self.yandex_cloud_folder:
            raise ValueError("Set YANDEX_CLOUD_FOLDER")
        return f"gpt://{self.yandex_cloud_folder}/{self.yandex_speech_model}"


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
