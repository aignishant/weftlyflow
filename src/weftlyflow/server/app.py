"""FastAPI app factory.

Wires:

* Structlog configuration.
* Async SQLAlchemy engine + session factory.
* Alembic-managed schema (auto-upgraded in dev, verified in prod).
* First-boot admin + project seed.
* Node registry with built-in nodes preloaded.
* Request-id + access-log middleware.
* Domain-exception → HTTP-response handlers.
* All Phase-2 routers.

A module-level ``app`` is exposed so ``uvicorn weftlyflow.server.app:app`` just
works. Tests use :func:`create_app` to spin up isolated instances with
overridden settings/session factories.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from weftlyflow import __version__
from weftlyflow.auth.bootstrap import ensure_bootstrap_admin
from weftlyflow.config import get_settings
from weftlyflow.config.logging import configure_logging
from weftlyflow.credentials.cipher import CredentialCipher, generate_key
from weftlyflow.credentials.external import (
    EnvSecretProvider,
    OnePasswordSecretProvider,
    SecretProviderRegistry,
    VaultSecretProvider,
)
from weftlyflow.credentials.registry import CredentialTypeRegistry
from weftlyflow.credentials.resolver import DatabaseCredentialResolver
from weftlyflow.db.base import Base
from weftlyflow.db.entities import (  # noqa: F401 — register tables on Base.metadata
    AuditEventEntity,
    CredentialEntity,
    ExecutionDataEntity,
    ExecutionEntity,
    OAuthStateEntity,
    ProjectEntity,
    RefreshTokenEntity,
    TriggerScheduleEntity,
    UserEntity,
    WebhookEntity,
    WorkflowEntity,
)
from weftlyflow.nodes.registry import NodeRegistry
from weftlyflow.server.errors import register_exception_handlers
from weftlyflow.server.middleware import RequestContextMiddleware
from weftlyflow.server.routers import auth as auth_router
from weftlyflow.server.routers import credentials as credentials_router
from weftlyflow.server.routers import executions as executions_router
from weftlyflow.server.routers import health as health_router
from weftlyflow.server.routers import metrics as metrics_router
from weftlyflow.server.routers import node_types as node_types_router
from weftlyflow.server.routers import oauth2 as oauth2_router
from weftlyflow.server.routers import sso as sso_router
from weftlyflow.server.routers import webhooks_ingress as webhooks_ingress_router
from weftlyflow.server.routers import workflows as workflows_router
from weftlyflow.triggers.leader import InMemoryLeaderLock
from weftlyflow.triggers.manager import ActiveTriggerManager
from weftlyflow.triggers.scheduler import InMemoryScheduler
from weftlyflow.webhooks.registry import WebhookRegistry
from weftlyflow.worker.queue import InlineExecutionQueue

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from weftlyflow.auth.sso.oidc import OIDCProvider
    from weftlyflow.auth.sso.saml import SAMLProvider
    from weftlyflow.config.settings import WeftlyflowSettings

log = structlog.get_logger(__name__)


def _build_oidc_provider(settings: WeftlyflowSettings) -> OIDCProvider | None:
    """Construct the OIDC provider from settings, or return ``None`` when disabled.

    Raises:
        RuntimeError: when ``sso_oidc_enabled`` is true but one of the four
            required ``sso_oidc_*`` settings is missing.
    """
    if not settings.sso_oidc_enabled:
        return None

    from weftlyflow.auth.sso.oidc import OIDCConfig, OIDCProvider  # noqa: PLC0415

    missing = [
        name
        for name, value in (
            ("WEFTLYFLOW_SSO_OIDC_ISSUER_URL", settings.sso_oidc_issuer_url),
            ("WEFTLYFLOW_SSO_OIDC_CLIENT_ID", settings.sso_oidc_client_id),
            (
                "WEFTLYFLOW_SSO_OIDC_CLIENT_SECRET",
                settings.sso_oidc_client_secret.get_secret_value(),
            ),
            ("WEFTLYFLOW_SSO_OIDC_REDIRECT_URI", settings.sso_oidc_redirect_uri),
        )
        if not value
    ]
    if missing:
        msg = f"sso_oidc_enabled=true but missing required settings: {', '.join(missing)}"
        raise RuntimeError(msg)
    return OIDCProvider(
        OIDCConfig(
            issuer_url=settings.sso_oidc_issuer_url,
            client_id=settings.sso_oidc_client_id,
            client_secret=settings.sso_oidc_client_secret.get_secret_value(),
            redirect_uri=settings.sso_oidc_redirect_uri,
            scopes=tuple(settings.sso_oidc_scope_list),
        ),
    )


def _build_credential_stack(
    settings: WeftlyflowSettings,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[CredentialCipher, CredentialTypeRegistry, DatabaseCredentialResolver]:
    """Assemble the credential cipher + type registry + resolver triple.

    Split out of :func:`lifespan` so the boot sequence stays under the
    PLR0915 budget. No side effects beyond instantiating the three objects.
    """
    encryption_key = settings.encryption_key.get_secret_value()
    if not encryption_key:
        encryption_key = generate_key()
        log.warning("encryption_key_missing_using_ephemeral")
    cipher = CredentialCipher(
        encryption_key,
        old_keys=[k.strip() for k in settings.encryption_key_old_keys.split(",") if k.strip()],
    )
    types = CredentialTypeRegistry()
    types.load_builtins()
    resolver = DatabaseCredentialResolver(
        session_factory=session_factory,
        cipher=cipher,
        types=types,
    )
    return cipher, types, resolver


def _build_saml_provider(settings: WeftlyflowSettings) -> SAMLProvider | None:
    """Construct the SAML provider from settings, or return ``None`` when disabled.

    Raises:
        RuntimeError: when ``sso_saml_enabled`` is true but a required
            setting is missing, or when ``python3-saml`` is not installed.
    """
    if not settings.sso_saml_enabled:
        return None

    try:
        from weftlyflow.auth.sso.saml import SAMLConfig, SAMLProvider  # noqa: PLC0415
    except ImportError as exc:
        msg = (
            "sso_saml_enabled=true but python3-saml is not installed — "
            "install with 'pip install weftlyflow[sso]'"
        )
        raise RuntimeError(msg) from exc

    _require_settings(
        "sso_saml",
        (
            ("WEFTLYFLOW_SSO_SAML_SP_ENTITY_ID", settings.sso_saml_sp_entity_id),
            ("WEFTLYFLOW_SSO_SAML_SP_ACS_URL", settings.sso_saml_sp_acs_url),
            ("WEFTLYFLOW_SSO_SAML_IDP_METADATA_XML", settings.sso_saml_idp_metadata_xml),
        ),
    )
    return SAMLProvider(
        SAMLConfig(
            sp_entity_id=settings.sso_saml_sp_entity_id,
            sp_acs_url=settings.sso_saml_sp_acs_url,
            idp_metadata_xml=settings.sso_saml_idp_metadata_xml,
            x509_cert=settings.sso_saml_sp_x509_cert,
            private_key=settings.sso_saml_sp_private_key.get_secret_value(),
            want_assertions_signed=settings.sso_saml_want_assertions_signed,
        ),
    )


def _build_secret_provider_registry(
    settings: WeftlyflowSettings,
) -> SecretProviderRegistry:
    """Assemble the global secret-provider registry from settings.

    ``EnvSecretProvider`` is always registered — it has no configuration and
    is the fallback that dev environments rely on. Other providers are
    opt-in via their ``*_enabled`` flag; enabling one without populating the
    required settings fails fast at boot.

    Raises:
        RuntimeError: when a ``*_enabled`` flag is true but one of the
            required settings for that provider is blank.
    """
    secret_registry = SecretProviderRegistry()
    secret_registry.register(EnvSecretProvider())

    if settings.vault_enabled:
        _require_settings(
            "vault",
            (
                ("WEFTLYFLOW_VAULT_ADDRESS", settings.vault_address),
                ("WEFTLYFLOW_VAULT_TOKEN", settings.vault_token.get_secret_value()),
            ),
        )
        secret_registry.register(
            VaultSecretProvider(
                address=settings.vault_address,
                token=settings.vault_token.get_secret_value(),
                namespace=settings.vault_namespace,
                timeout_seconds=settings.vault_timeout_seconds,
            ),
        )

    if settings.onepassword_enabled:
        _require_settings(
            "onepassword",
            (
                ("WEFTLYFLOW_ONEPASSWORD_CONNECT_URL", settings.onepassword_connect_url),
                (
                    "WEFTLYFLOW_ONEPASSWORD_CONNECT_TOKEN",
                    settings.onepassword_connect_token.get_secret_value(),
                ),
            ),
        )
        secret_registry.register(
            OnePasswordSecretProvider(
                connect_url=settings.onepassword_connect_url,
                token=settings.onepassword_connect_token.get_secret_value(),
                timeout_seconds=settings.onepassword_timeout_seconds,
            ),
        )

    if settings.aws_secrets_enabled:
        # Lazy import — boto3 only lands in the install when the
        # ``aws-secrets`` extra is requested.
        try:
            from weftlyflow.credentials.external.aws_provider import (  # noqa: PLC0415
                AWSSecretsManagerProvider,
            )
        except ImportError as exc:
            msg = (
                "aws_secrets_enabled=true but boto3 is not installed — "
                "install with 'pip install weftlyflow[aws-secrets]'"
            )
            raise RuntimeError(msg) from exc
        secret_registry.register(
            AWSSecretsManagerProvider(
                region_name=settings.aws_secrets_region or None,
            ),
        )

    return secret_registry


def _require_settings(provider: str, pairs: tuple[tuple[str, str], ...]) -> None:
    """Raise ``RuntimeError`` listing every blank env-var in ``pairs``.

    Args:
        provider: Short provider identifier used in the error message
            (e.g. ``"vault"``).
        pairs: Sequence of ``(env_var_name, current_value)``. Any pair
            whose value is falsy is reported as missing.
    """
    missing = [name for name, value in pairs if not value]
    if missing:
        msg = f"{provider}_enabled=true but missing required settings: {', '.join(missing)}"
        raise RuntimeError(msg)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap shared resources at startup, tear down at shutdown."""
    settings = get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)
    log.info("weftlyflow_starting", version=__version__, env=settings.env)

    engine: AsyncEngine = create_async_engine(settings.database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    registry = NodeRegistry()
    registry.load_builtins()

    async with session_factory() as session:
        await ensure_bootstrap_admin(
            session,
            settings,
            admin_email_env=os.getenv("WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL"),
            admin_password_env=os.getenv("WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD"),
        )
        await session.commit()

    credential_cipher, credential_types, credential_resolver = _build_credential_stack(
        settings,
        session_factory,
    )

    webhook_registry = WebhookRegistry()
    scheduler = InMemoryScheduler()
    leader = InMemoryLeaderLock(instance_id="api")
    leader.acquire()
    execution_queue = InlineExecutionQueue(
        session_factory=session_factory,
        registry=registry,
        credential_resolver=credential_resolver,
    )
    trigger_manager = ActiveTriggerManager(
        session_factory=session_factory,
        registry=webhook_registry,
        scheduler=scheduler,
        queue=execution_queue,
        leader=leader,
    )
    await trigger_manager.warm_up()
    scheduler.start()

    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.node_registry = registry
    app.state.webhook_registry = webhook_registry
    app.state.execution_queue = execution_queue
    app.state.trigger_manager = trigger_manager
    app.state.scheduler = scheduler
    app.state.leader_lock = leader
    app.state.credential_cipher = credential_cipher
    app.state.credential_types = credential_types
    app.state.credential_resolver = credential_resolver
    app.state.secret_provider_registry = _build_secret_provider_registry(settings)

    app.state.sso_oidc_provider = _build_oidc_provider(settings)
    app.state.sso_saml_provider = _build_saml_provider(settings)

    try:
        yield
    finally:
        scheduler.shutdown()
        leader.release()
        await engine.dispose()
        log.info("weftlyflow_stopped")


def create_app() -> FastAPI:
    """Return a fresh FastAPI instance wired with middleware, handlers, routers."""
    settings = get_settings()

    app = FastAPI(
        title="Weftlyflow",
        version=__version__,
        description="Workflow automation platform.",
        lifespan=lifespan,
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
        openapi_url="/api/v1/openapi.json",
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router.router)
    app.include_router(metrics_router.router)
    app.include_router(auth_router.router)
    app.include_router(workflows_router.router)
    app.include_router(executions_router.router)
    app.include_router(node_types_router.router)
    app.include_router(credentials_router.router)
    app.include_router(credentials_router.credential_types_router)
    app.include_router(oauth2_router.router)
    app.include_router(sso_router.router)
    app.include_router(sso_router.saml_router)
    app.include_router(webhooks_ingress_router.router)

    return app


app = create_app()
