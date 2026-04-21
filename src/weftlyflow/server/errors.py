"""Map :class:`weftlyflow.domain.errors.WeftlyflowError` subclasses to HTTP responses.

Registered once via :func:`register_exception_handlers` during app startup.
Keeps HTTP concerns out of the domain — raise the right exception anywhere
and the server turns it into a structured JSON error response.

Error envelope::

    {
        "error": {
            "code": "workflow_validation",
            "message": "...",
            "detail": "..."
        }
    }
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog
from fastapi import status
from fastapi.responses import JSONResponse

from weftlyflow.domain.errors import (
    CredentialDecryptError,
    CredentialNotFoundError,
    CycleDetectedError,
    ExpressionEvalError,
    ExpressionSyntaxError,
    ExpressionTimeoutError,
    InvalidConnectionError,
    NodeExecutionError,
    WeftlyflowError,
    WorkflowValidationError,
)
from weftlyflow.engine.errors import NodeTypeNotFoundError

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

_log = structlog.get_logger(__name__)


_ERROR_CODE_BY_TYPE: dict[type[WeftlyflowError], str] = {
    WorkflowValidationError: "workflow_validation",
    InvalidConnectionError: "invalid_connection",
    CycleDetectedError: "cycle_detected",
    NodeExecutionError: "node_execution_error",
    CredentialNotFoundError: "credential_not_found",
    CredentialDecryptError: "credential_decrypt_error",
    ExpressionSyntaxError: "expression_syntax_error",
    ExpressionEvalError: "expression_eval_error",
    ExpressionTimeoutError: "expression_timeout",
    NodeTypeNotFoundError: "unknown_node_type",
}


_STATUS_BY_TYPE: dict[type[WeftlyflowError], int] = {
    WorkflowValidationError: status.HTTP_400_BAD_REQUEST,
    InvalidConnectionError: status.HTTP_400_BAD_REQUEST,
    CycleDetectedError: status.HTTP_400_BAD_REQUEST,
    CredentialNotFoundError: status.HTTP_404_NOT_FOUND,
    NodeTypeNotFoundError: status.HTTP_400_BAD_REQUEST,
}


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the Weftlyflow-specific exception handlers onto ``app``."""
    app.add_exception_handler(WeftlyflowError, _weftlyflow_handler)


async def _weftlyflow_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, WeftlyflowError)
    code = _ERROR_CODE_BY_TYPE.get(type(exc), "weftlyflow_error")
    http_status = _STATUS_BY_TYPE.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": str(exc),
        },
    }
    _log.warning("weftlyflow_error", code=code, status=http_status, message=str(exc))
    return JSONResponse(status_code=http_status, content=payload)
