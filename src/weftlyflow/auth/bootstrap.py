"""First-boot administrator + default project seed.

Runs once per process as part of the FastAPI lifespan. Behaviour:

* If the ``users`` table is non-empty, do nothing.
* If ``WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL`` + ``..._PASSWORD`` are set, create
  that admin + a personal project for them.
* Otherwise, in development mode, auto-generate a random password, log it at
  warning level, and create a default ``admin@weftlyflow.local`` account.
* In production mode with neither env var set, raise — the operator must
  supply credentials explicitly.

This keeps dev frictionless (``make dev-api`` just works) while forcing
production deployments to make a deliberate choice.
"""

from __future__ import annotations

import secrets
import string
from typing import TYPE_CHECKING

import structlog

from weftlyflow.auth.constants import PROJECT_KIND_PERSONAL, ROLE_OWNER
from weftlyflow.auth.passwords import hash_password
from weftlyflow.db.repositories.project_repo import ProjectRepository
from weftlyflow.db.repositories.user_repo import UserRepository
from weftlyflow.domain.ids import new_project_id, new_user_id

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from weftlyflow.config.settings import WeftlyflowSettings

_log = structlog.get_logger(__name__)
# ``.local`` is a reserved special-use TLD (RFC 6761) and rejected by
# email-validator; ``.io`` is a public TLD accepted without surprise.
_DEFAULT_ADMIN_EMAIL: str = "admin@weftlyflow.io"


class BootstrapError(RuntimeError):
    """Raised when production credentials are missing at first boot."""


async def ensure_bootstrap_admin(
    session: AsyncSession,
    settings: WeftlyflowSettings,
    *,
    admin_email_env: str | None,
    admin_password_env: str | None,
) -> None:
    """Create the admin + default project if the database has no users yet.

    Args:
        session: A live :class:`AsyncSession` — the caller is responsible for
            committing.
        settings: Runtime settings; used to decide dev vs. production behaviour.
        admin_email_env: Optional email from env (tests pass None).
        admin_password_env: Optional password from env (tests pass None).

    Raises:
        BootstrapError: production boot with no credentials configured.
    """
    user_repo = UserRepository(session)
    if await user_repo.count() > 0:
        return

    email, password, generated = _resolve_credentials(
        admin_email_env=admin_email_env,
        admin_password_env=admin_password_env,
        is_prod=settings.is_prod,
    )

    project_repo = ProjectRepository(session)
    project_id = new_project_id()
    await project_repo.create(
        project_id=project_id,
        name="Personal",
        kind=PROJECT_KIND_PERSONAL,
        owner_id="",  # overwritten below once we have the user id.
    )
    user_id = new_user_id()
    await user_repo.create(
        user_id=user_id,
        email=email,
        password_hash=hash_password(password),
        display_name="Administrator",
        global_role=ROLE_OWNER,
        default_project_id=project_id,
    )

    # Patch the project's owner now that the user exists.
    from weftlyflow.db.entities.project import ProjectEntity  # noqa: PLC0415

    project_entity = await session.get(ProjectEntity, project_id)
    if project_entity is not None:
        project_entity.owner_id = user_id
    await session.flush()

    if generated:
        _log.warning(
            "bootstrap_admin_generated",
            email=email,
            password=password,
            note=(
                "Weftlyflow generated a first-boot admin account. Save the "
                "password — it will not be printed again. Set "
                "WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL and _PASSWORD to pre-seed."
            ),
        )
    else:
        _log.info("bootstrap_admin_created", email=email)


def _resolve_credentials(
    *,
    admin_email_env: str | None,
    admin_password_env: str | None,
    is_prod: bool,
) -> tuple[str, str, bool]:
    if admin_email_env and admin_password_env:
        return admin_email_env, admin_password_env, False
    if is_prod:
        msg = (
            "Production boot requires WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL and "
            "WEFTLYFLOW_BOOTSTRAP_ADMIN_PASSWORD to be set. Refusing to "
            "auto-generate credentials in production."
        )
        raise BootstrapError(msg)
    return _DEFAULT_ADMIN_EMAIL, _random_password(), True


def _random_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))
