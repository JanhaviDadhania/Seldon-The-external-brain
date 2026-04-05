from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "twitter_poster.db"


class Settings(BaseSettings):
    app_name: str = "twitter-poster-backend"
    environment: str = "development"
    database_url: str = f"sqlite:///{DEFAULT_DB_PATH}"
    use_ollama_for_internal_tags: bool = True
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_tag_model: str = "qwen2.5:3b-instruct"
    ollama_narrative_model: str = "qwen2.5:3b-instruct"
    ollama_tag_batch_size: int = 20
    ollama_timeout_seconds: float = 30.0
    embedding_model_name: str = "sentence-transformers/all-mpnet-base-v2"
    preload_embedding_model_on_startup: bool = False
    embedding_batch_size: int = 10
    candidate_retrieval_limit: int = 10
    telegram_bot_token: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_poll_limit: int = 25
    public_url: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_prefix="TWITTER_POSTER_",
        case_sensitive=False,
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
