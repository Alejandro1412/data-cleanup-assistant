from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("./data")
    max_upload_mb: int = 20
    max_rows: int = 100_000
    cors_origins: list[str] = ["http://localhost:5173"]

    anthropic_api_key: str | None = None
    llm_model: str = "claude-sonnet-5-5"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3

    # Upper bounds on how much data a single analysis may send to the model.
    llm_max_categorical_columns: int = 10
    llm_max_distinct_values: int = 200
    llm_max_duplicate_pairs: int = 60
    llm_max_review_rows: int = 60

    default_phone_region: str = "US"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
