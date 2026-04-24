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

    # --- SSO (SAML 2.0) ---
    sso_saml_enabled: bool = Field(
        default=False,
        description=(
            "Mount the ``/api/v1/auth/sso/saml/*`` routes. Requires the "
            "``sso_saml_*`` settings below to be populated and the ``sso`` "
            "optional extra installed (``pip install 'weftlyflow[sso]'``)."
        ),
    )
    sso_saml_sp_entity_id: str = Field(
        default="",
        description=(
            "The Service Provider's entity ID. Usually the fully-qualified "
            "metadata URL, e.g. "
            "``https://weftlyflow.example.com/api/v1/auth/sso/saml/metadata``."
        ),
    )
    sso_saml_sp_acs_url: str = Field(
        default="",
        description=(
            "Fully-qualified HTTPS URL of the SP's Assertion Consumer Service "
            "— e.g. ``https://weftlyflow.example.com/api/v1/auth/sso/saml/acs``. "
            "Must match the value registered with the IdP exactly."
        ),
    )
    sso_saml_idp_metadata_xml: str = Field(
        default="",
        description=(
            "Full IdP metadata XML document. Paste the contents verbatim; "
            "the adapter parses the IdP's SSO endpoint, entity ID, and "
            "signing cert from it at server boot."
        ),
    )
    sso_saml_sp_x509_cert: str = Field(
        default="",
        description=(
            "Optional PEM-encoded SP signing cert. When both this and "
            "``sso_saml_sp_private_key`` are set, AuthnRequests are signed."
        ),
    )
    sso_saml_sp_private_key: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "Optional PEM-encoded SP signing key. Pairs with "
            "``sso_saml_sp_x509_cert``."
        ),
    )
    sso_saml_want_assertions_signed: bool = Field(
        default=True,
        description=(
            "Require the IdP's assertion XML be signed. Keep true outside "
            "of local development — unsigned assertions are trivially "
            "forgeable."
        ),
    )
    sso_saml_auto_provision: bool = Field(
        default=True,
        description=(
            "When true, first-time SAML logins create a local user row + "
            "personal project. Disable to require pre-provisioning."
        ),
    )
    sso_nonce_store_backend: str = Field(
        default="memory",
        description=(
            "Backend for the SSO replay-protection nonce store. ``memory`` "
            "is process-local and correct for single-instance deployments. "
            "``redis`` uses ``SET NX EX`` against the configured Redis URL "
            "so horizontally scaled API pods share a single consumed-nonce "
            "set and stay replay-safe across instances."
        ),
    )
    sso_nonce_store_redis_url: str = Field(
        default="",
        description=(
            "Override Redis URL for the nonce store. When blank and "
            "``sso_nonce_store_backend='redis'``, the shared "
            "``redis_url`` setting is used."
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

    # --- external secret providers (1Password Connect) ---
    onepassword_enabled: bool = Field(
        default=False,
        description=(
            "Register the ``OnePasswordSecretProvider`` so credentials can "
            "reference ``op:vaults/<uuid>/items/<uuid>#<field>`` paths. "
            "Requires ``onepassword_connect_url`` and ``onepassword_connect_token``."
        ),
    )
    onepassword_connect_url: str = Field(
        default="",
        description="Base URL of the 1Password Connect server — e.g. ``http://connect:8080``.",
    )
    onepassword_connect_token: SecretStr = Field(
        default=SecretStr(""),
        description="1Password Connect bearer token.",
    )
    onepassword_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="Per-request HTTP timeout when reading from 1Password Connect.",
    )

    # --- external secret providers (AWS Secrets Manager) ---
    aws_secrets_enabled: bool = Field(
        default=False,
        description=(
            "Register the ``AWSSecretsManagerProvider`` so credentials can "
            "reference ``aws:<secret-id>[#<field>]`` paths. Requires the "
            "``aws-secrets`` optional extra (``pip install 'weftlyflow[aws-secrets]'``). "
            "Credentials come from the standard boto3 chain — static env vars, "
            "IAM role on EC2, IRSA on EKS, ECS task roles, etc."
        ),
    )
    aws_secrets_region: str = Field(
        default="",
        description=(
            "AWS region for Secrets Manager lookups. Empty string defers to "
            "the boto3 region chain (``AWS_REGION`` / ``AWS_DEFAULT_REGION``)."
        ),
    )

    # --- execution-data storage ---
    execution_data_backend: str = Field(
        default="db",
        description=(
            "Backend used for the bulky ``workflow_snapshot`` + ``run_data`` "
            "pair attached to each execution. ``db`` inlines them in the "
            "``execution_data`` row (simple, but grows the DB). ``fs`` writes "
            "one JSON file per execution under ``execution_data_fs_path`` and "
            "keeps only a pointer in the row — use this when you need to "
            "expire or archive old payloads without touching Postgres."
        ),
    )
    execution_data_fs_path: str = Field(
        default="",
        description=(
            "Base directory for the filesystem execution-data backend. Required "
            "when ``execution_data_backend='fs'``. Files are laid out as "
            "``<path>/<yyyy>/<mm>/<execution_id>.json``; the directory is "
            "created on first write. Point this at a volume with enough "
            "headroom for your retention window."
        ),
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
