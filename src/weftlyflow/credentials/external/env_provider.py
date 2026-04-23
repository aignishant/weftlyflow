"""Environment-variable secret provider.

The simplest backend: resolves ``env:VAR_NAME`` references by reading
``os.environ`` at lookup time. Always available, requires zero config,
ideal for developer machines and for CI.

Security notes:

* The field fragment (``env:FOO#bar``) is rejected — an environment
  variable is a flat string, so carrying a ``#field`` is always a mistake.
* The lookup happens *on every call* rather than being cached at process
  start, so rotating an env var and restarting the process is not required
  as long as the parent container can update the variable (rare in
  practice, but keeps the provider predictable).
"""

from __future__ import annotations

import os

from weftlyflow.credentials.external.base import (
    SecretNotFoundError,
    SecretProviderError,
    SecretReference,
)


class EnvSecretProvider:
    """Read-only provider backed by :data:`os.environ`."""

    scheme: str = "env"

    __slots__ = ("_env",)

    def __init__(self, env: dict[str, str] | None = None) -> None:
        """Bind to an override dict or the live ``os.environ``.

        Args:
            env: Optional mapping used in place of ``os.environ``. Primarily
                a test seam — production callers pass ``None``.
        """
        self._env = env

    async def get(self, reference: SecretReference) -> str:
        """Return ``os.environ[reference.path]`` or raise.

        Raises:
            SecretProviderError: If the reference carries a ``#field`` (env
                vars are scalar strings).
            SecretNotFoundError: If the variable is unset.
        """
        if reference.scheme != self.scheme:
            msg = f"EnvSecretProvider cannot handle scheme {reference.scheme!r}"
            raise SecretProviderError(msg)
        if reference.field is not None:
            msg = "env references do not support a #field fragment"
            raise SecretProviderError(msg)
        source = self._env if self._env is not None else os.environ
        try:
            return source[reference.path]
        except KeyError as exc:
            msg = f"environment variable {reference.path!r} is not set"
            raise SecretNotFoundError(msg) from exc
