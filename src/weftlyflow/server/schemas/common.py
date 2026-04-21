"""Shared DTO primitives used across multiple routers.

Nothing here knows about domain dataclasses — these are wire-format types
only. Translation happens in the routers.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WeftlyflowModel(BaseModel):
    """Project-wide Pydantic base with consistent configuration."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class PageParams(WeftlyflowModel):
    """Pagination bounds reused by every list endpoint."""

    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page[T](WeftlyflowModel):
    """Typed list-response envelope (PEP 695 generic)."""

    items: list[T]
    limit: int
    offset: int
    total: int | None = None
