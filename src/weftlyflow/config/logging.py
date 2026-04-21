"""Structured logging setup for Weftlyflow.

We use :mod:`structlog` on top of the stdlib ``logging`` module. Call
:func:`configure_logging` once at process start (from the API lifespan, the
Celery ``worker_init`` signal, and the CLI entry point).

Every logger binds context via ``structlog.contextvars.bind_contextvars`` so
request/execution IDs flow automatically without threading them through
function arguments.

Example:
    >>> import structlog
    >>> log = structlog.get_logger(__name__)
    >>> log.info("workflow_started", workflow_id="wf_1", items=42)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from weftlyflow.config.settings import LogFormat, LogLevel


def configure_logging(level: LogLevel = "info", fmt: LogFormat = "console") -> None:
    """Configure stdlib logging and structlog.

    Args:
        level: Minimum log level for both stdlib and structlog.
        fmt: ``console`` for dev (pretty, colored, multi-line) or ``json`` for
            prod (single-line newline-delimited JSON, ready for log aggregators).

    Idempotent: calling twice reconfigures cleanly.
    """
    stdlib_level = getattr(logging, level.upper())

    # stdlib
    logging.basicConfig(
        format="%(message)s",
        level=stdlib_level,
        stream=sys.stdout,
        force=True,
    )

    # shared processor chain
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        _redact_secrets,
    ]

    if fmt == "json":
        processors.append(structlog.processors.format_exc_info)
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(
            structlog.dev.ConsoleRenderer(
                colors=True,
                exception_formatter=structlog.dev.plain_traceback,
            ),
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(stdlib_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


_SECRET_KEYS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "authorization",
        "api_key",
        "apikey",
        "api-key",
        "private_key",
        "access_token",
        "refresh_token",
        "data_ciphertext",
        "encryption_key",
    },
)

_SECRET_SUBSTRINGS: tuple[str, ...] = ("password", "secret", "token", "api_key")


def _redact_secrets(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Replace any value whose key looks secret with ``'***'``.

    Applied as a structlog processor early in the chain so secrets never reach
    the renderer — they're dropped before stringification.
    """
    for key in list(event_dict.keys()):
        lowered = key.lower()
        if lowered in _SECRET_KEYS or any(s in lowered for s in _SECRET_SUBSTRINGS):
            event_dict[key] = "***"
    return event_dict
