"""Node-type catalog DTOs — reshaped :class:`NodeSpec` for the frontend."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from weftlyflow.server.schemas.common import WeftlyflowModel


class PropertyOptionDTO(WeftlyflowModel):
    """Dropdown option for ``options``/``multi_options`` properties."""

    value: str
    label: str
    description: str | None = None


class PropertySchemaDTO(WeftlyflowModel):
    """Single parameter definition on a node."""

    name: str
    display_name: str
    type: str
    default: Any = None
    required: bool = False
    description: str | None = None
    options: list[PropertyOptionDTO] | None = None
    placeholder: str | None = None
    type_options: dict[str, Any] | None = None


class NodeTypeResponse(WeftlyflowModel):
    """Catalog entry — one per registered ``(type, version)``."""

    type: str
    version: int
    display_name: str
    description: str
    icon: str
    category: str
    group: list[str] = Field(default_factory=list)
    supports_binary: bool = False
    properties: list[PropertySchemaDTO] = Field(default_factory=list)
