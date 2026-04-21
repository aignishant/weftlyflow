"""Environment-driven configuration for Weftlyflow.

All values are read from environment variables prefixed ``WEFTLYFLOW_`` and
validated through Pydantic v2. The object is cached via ``@lru_cache`` so every
caller sees the same instance within a process — call ``get_settings.cache_clear()``
in tests if you need to re-read.

Example:
    >>> from weftlyflow.config import get_settings
    >>> settings = get_settings()
    >>> settings.database_url.scheme
    'sqlite'

See also:
    - IMPLEMENTATION_BIBLE.md §4 for the rationale behind each choice.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["console", "json"]
LogLevel = Literal["debug", "info", "warning", "error", "critical"]
Env = Literal["development", "production", "test"]


class WeftlyflowSettings(BaseSettings):
    """Top-level settings bag.

    Every attribute is typed and validated; unknown ``WEFTLYFLOW_*`` env vars are
    ignored so this class does not break when a future feature adds new variables
    to ``.env`` files already present in users' installations.
    """

    model_config = SettingsConfigDict(
        env_prefix="WEFTLYFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- core ---
    env: Env = "development"
    log_level: LogLevel = "info"
    log_format: LogFormat = "console"
    secret_key: SecretStr = Field(default=SecretStr("change-me"), description="JWT HMAC key")

    # --- data ---
    database_url: str = "sqlite+aiosqlite:///./data/weftlyflow.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- crypto ---
    encryption_key: SecretStr = Field(default=SecretStr(""), description="Fernet key (base64)")
    encryption_key_old_keys: str = Field(default="", description="Comma-separated old keys")

    # --- server ---
    host: str = "0.0.0.0"
    port: int = 5678
    public_url: str = "http://localhost:5678"
    cors_origins: str = "http://localhost:5173"

    # --- features ---
    registration_enabled: bool = True
    mfa_required: bool = False
    community_nodes_dir: str = ""

    # --- observability ---
    metrics_enabled: bool = True
    tracing_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    sentry_dsn: str = ""

    # --- derived ---
    @property
    def cors_origin_list(self) -> list[str]:
        """Parse ``cors_origins`` into a list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_dev(self) -> bool:
        """True when running in development mode."""
        return self.env == "development"

    @property
    def is_prod(self) -> bool:
        """True when running in production mode."""
        return self.env == "production"


@lru_cache(maxsize=1)
def get_settings() -> WeftlyflowSettings:
    """Return a singleton `WeftlyflowSettings` instance.

    Returns:
        The cached settings object. First call parses the environment; subsequent
        calls return the same instance until ``get_settings.cache_clear()`` is
        invoked (used in tests).
    """
    return WeftlyflowSettings()
