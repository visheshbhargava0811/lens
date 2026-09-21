"""Application settings loaded from the environment and `.env` files."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", REPO_ROOT / "infra" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["dev", "test", "staging", "prod"] = "dev"
    log_level: str = "INFO"

    # Local defaults match infra/docker-compose.yml. Real deployments set these via env.
    database_url: str = "postgresql+psycopg://lens:lens@localhost:5433/lens"
    redis_url: str = "redis://localhost:6380/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr | None = None

    langsmith_tracing: bool = False
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "lens-dev"

    web_origin: str = "http://localhost:3000"

    # Ingestion. The user agent names the crawler honestly; robots.txt rules are matched against "LensBot".
    ingest_user_agent: str = "LensBot/0.1 (news comparison research prototype)"
    ingest_robots_token: str = "LensBot"
    ingest_default_interval_min: int = 15
    # Per-fetch LangSmith traces cost quota (about 2k traces/day at 20 sources); off by default.
    ingest_trace: bool = False
    config_dir: Path = Field(default=REPO_ROOT / "config")


@lru_cache
def get_settings() -> Settings:
    return Settings()
