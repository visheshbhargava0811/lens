"""Application settings loaded from the environment and `.env` files."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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

    # LLM providers (config/models.yaml picks tier -> provider/model; ADR-0022).
    groq_api_key: SecretStr | None = None
    groq_api_key_2: SecretStr | None = None  # second key: `account: 2` entries in config/models.yaml
    groq_api_key_3: SecretStr | None = None  # third key: Ask's own quota (`account: 3`, ADR-0032)
    sarvam_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None  # fallback provider (config/models.yaml `fallbacks`)
    google_factcheck_api_key: SecretStr | None = None  # Fact Check Tools API (ClaimReview), docs/04 section 9
    llm_timeout_s: float = 120.0

    web_origin: str = "http://localhost:3000"
    api_public_url: str = "http://localhost:8000"  # this API as browsers reach it (OAuth redirect URI, ADR-0044)
    google_client_id: str | None = None  # Google sign-in (ADR-0044); unset hides the sign-in button
    google_client_secret: SecretStr | None = None
    admin_token: SecretStr | None = None  # /api/v1/admin/*; unset disables admin endpoints
    rate_limit_salt: SecretStr | None = None  # shared across API workers (lens.guardrails.input.client_key)
    max_body_bytes: int = 1_000_000  # request bodies above this are refused (admin CSV import: 5x)

    # Ingestion. The user agent names the crawler honestly; robots.txt rules are matched against "LensBot".
    ingest_user_agent: str = "LensBot/0.1 (news comparison research prototype)"
    ingest_robots_token: str = "LensBot"
    ingest_default_interval_min: int = 15
    # Per-fetch LangSmith traces cost quota (about 2k traces/day at 20 sources); off by default.
    ingest_trace: bool = False
    config_dir: Path = Field(default=REPO_ROOT / "config")

    @field_validator("*", mode="before")
    @classmethod
    def _empty_is_unset(cls, v: object) -> object:
        """`KEY=` in a .env file means unset, never an empty secret: an empty ADMIN_TOKEN once meant an empty
        bearer header matched it (pre-deploy checklist, ADR-0042)."""
        return None if isinstance(v, str) and v.strip() == "" else v

    @property
    def deployed(self) -> bool:
        return self.app_env in ("staging", "prod")

    @model_validator(mode="after")
    def _safe_for_deployment(self) -> "Settings":
        """Staging and prod refuse to start on dev defaults or weak secrets (pre-deploy security checklist)."""
        if not self.deployed:
            return self
        problems = []
        if "lens:lens@" in self.database_url or "localhost" in self.database_url:
            problems.append("DATABASE_URL still uses the local dev database or password")
        if "sslmode=require" not in self.database_url and "sslmode=verify" not in self.database_url:
            problems.append("DATABASE_URL must use TLS (sslmode=require or verify-full)")
        if self.redis_url.startswith("redis://localhost") or "@" not in self.redis_url:
            problems.append("REDIS_URL needs a password (redis://:<password>@host or rediss://)")
        if self.qdrant_api_key is None:
            problems.append("QDRANT_API_KEY is not set")
        if not self.web_origin.startswith("https://"):
            problems.append("WEB_ORIGIN must be an https:// origin")
        if self.admin_token is not None and len(self.admin_token.get_secret_value()) < 32:
            problems.append("ADMIN_TOKEN must be at least 32 characters (or unset to disable admin)")
        if self.rate_limit_salt is None:
            problems.append("RATE_LIMIT_SALT is not set (rate limits would differ per worker)")
        if self.log_level.upper() == "DEBUG":
            problems.append("LOG_LEVEL=DEBUG is not allowed outside dev")
        if self.google_client_id and not self.api_public_url.startswith("https://"):
            problems.append("API_PUBLIC_URL must be https:// when Google sign-in is on")
        if bool(self.google_client_id) != bool(self.google_client_secret):
            problems.append("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set together")
        if problems:
            raise ValueError("unsafe settings for " + self.app_env + ": " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
