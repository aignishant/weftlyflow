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

See Also:
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
    enable_code_node: bool = Field(
        default=False,
        description=(
            "Register the ``weftlyflow.code`` node. Off by default; turn on "
            "only after the operator has reviewed the code-node threat model "
            "(IMPLEMENTATION_BIBLE.md §26 risk #2). When enabled, snippets "
            "execute in a subprocess sandbox with the limits below applied."
        ),
    )
    code_node_cpu_seconds: int = Field(
        default=5,
        description="RLIMIT_CPU applied to each Code-node subprocess.",
        gt=0,
    )
    code_node_memory_bytes: int = Field(
        default=256 * 1024 * 1024,
        description="RLIMIT_AS applied to each Code-node subprocess (bytes).",
        gt=0,
    )
    code_node_wall_clock_seconds: float = Field(
        default=10.0,
        description=(
            "Hard wall-clock ceiling per Code-node invocation, enforced by "
            "the parent via ``subprocess.run(timeout=...)``. Must exceed "
            "``code_node_cpu_seconds`` so the CPU limit can fire first."
        ),
        gt=0.0,
    )
    expression_timeout_seconds: float = Field(
        default=2.0,
        description=(
            "Wall-clock budget for a single ``{{ ... }}`` expression. "
            "Exceeding this raises ``ExpressionTimeoutError`` and the node "
            "fails with a timeout marker. Keep small — a healthy expression "
            "returns in microseconds."
        ),
        gt=0.0,
    )
    worker_task_soft_time_limit_seconds: int = Field(
        default=300,
        description=(
            "Soft CPU budget per Celery task; raises ``SoftTimeLimitExceeded`` "
            "inside the task so cleanup code can run."
        ),
        gt=0,
    )
    worker_task_time_limit_seconds: int = Field(
        default=600,
        description=(
            "Hard wall-clock ceiling per Celery task. When exceeded the "
            "worker process is killed and the task is requeued. Must be "
            "greater than ``worker_task_soft_time_limit_seconds``."
        ),
        gt=0,
    )
    exposed_env_vars: str = Field(
        default="",
        description=(
            "Comma-separated list of environment variable names exposed to "
            "workflow expressions via ``$env``. The expression sandbox reads "
            "only these, never the full process environment. Empty by default "
            "so ``$env`` is an empty dict until the operator opts in."
        ),
    )

    # --- SSO (OIDC) ---
    sso_oidc_enabled: bool = Field(
        default=False,
        description=(
            "Mount the ``/api/v1/auth/sso/oidc/*`` routes. Requires the four "
            "``sso_oidc_*`` settings below to be populated; a misconfigured "
            "enable will fail fast at server boot rather than at first "
            "login."
        ),
    )
    sso_oidc_issuer_url: str = Field(
        default="",
        description=(
            "Base URL of the OIDC IdP — the adapter appends "
            "``/.well-known/openid-configuration`` to discover endpoints."
        ),
    )
    sso_oidc_client_id: str = ""
    sso_oidc_client_secret: SecretStr = Field(default=SecretStr(""))
    sso_oidc_redirect_uri: str = Field(
        default="",
        description=(
            "Fully-qualified callback URL registered with the IdP — e.g. "
            "``https://weftlyflow.example.com/api/v1/auth/sso/oidc/callback``. "
            "Must match what the IdP redirects to exactly."
        ),
    )
    sso_oidc_scopes: str = Field(
        default="openid email profile",
        description="Space-separated list of OAuth2 scopes sent on login.",
    )
    sso_oidc_auto_provision: bool = Field(
        default=True,
        description=(
            "When true, first-time SSO logins create a local user row + "
            "personal project. Disable to require pre-provisioning."
        ),
    )
    sso_post_login_redirect: str = Field(
        default="/",
        description=(
            "Relative or absolute URL the callback redirects to after a "
            "successful login. The access + refresh tokens are appended as "
            "fragment parameters (``#access_token=...&refresh_token=...``) "
            "so they never hit the server log."
        ),
    )

    # --- external secret providers (Vault) ---
    vault_enabled: bool = Field(
        default=False,
        description=(
            "Register the ``VaultSecretProvider`` with the secret-provider "
            "registry so credentials can reference ``vault:...`` paths. "
            "Requires ``vault_address`` and ``vault_token`` to be set."
        ),
    )
    vault_address: str = Field(
        default="",
        description="Base URL of the Vault server — e.g. ``https://vault:8200``.",
    )
    vault_token: SecretStr = Field(
        default=SecretStr(""),
        description="Vault token sent via the ``X-Vault-Token`` header.",
    )
    vault_namespace: str = Field(
        default="",
        description="Optional Vault Enterprise namespace (``X-Vault-Namespace`` header).",
    )
    vault_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Per-request HTTP timeout when reading from Vault.",
    )

    # --- audit ---
    audit_retention_days: int = Field(
        default=90,
        description=(
            "Number of whole days to keep ``audit_events`` rows before the "
            "retention beat task deletes them. Must be positive; set high "
            "enough to satisfy any applicable compliance regime."
        ),
        gt=0,
    )

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
    def sso_oidc_scope_list(self) -> list[str]:
        """Parse ``sso_oidc_scopes`` into a list."""
        return [s.strip() for s in self.sso_oidc_scopes.split() if s.strip()]

    @property
    def exposed_env_var_list(self) -> list[str]:
        """Parse ``exposed_env_vars`` into a list of variable names."""
        return [v.strip() for v in self.exposed_env_vars.split(",") if v.strip()]

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
