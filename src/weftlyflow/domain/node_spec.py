"""NodeSpec — declarative description of a node plugin.

Every built-in or community node exposes a :class:`NodeSpec` on its class. The
spec powers the frontend parameter-form generator, the node catalog endpoint
(``GET /api/v1/node-types``), and the engine's port-wiring logic.

See weftlyinfo.md §9 for the plugin architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from weftlyflow.domain.workflow import Port

PropertyType = Literal[
    "string",
    "number",
    "boolean",
    "options",
    "multi_options",
    "json",
    "datetime",
    "color",
    "expression",
    "credentials",
    "fixed_collection",
    "binary",
]


class NodeCategory(StrEnum):
    """Top-level category for UI grouping."""

    TRIGGER = "trigger"
    CORE = "core"
    INTEGRATION = "integration"
    AI = "ai"


@dataclass(frozen=True)
class PropertyOption:
    """One choice in an ``options`` / ``multi_options`` property."""

    value: str
    label: str
    description: str | None = None


@dataclass(frozen=True)
class DisplayOptions:
    """Conditional visibility for a property.

    A property is shown only when **all** conditions in ``show`` are satisfied
    and **none** in ``hide`` are. Conditions are ``{sibling_name: [allowed_values]}``.
    """

    show: dict[str, list[Any]] = field(default_factory=dict)
    hide: dict[str, list[Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PropertySchema:
    """One user-visible parameter of a node.

    The full set forms the schema the frontend renders as a form.

    Attributes:
        name: Dict key in ``Node.parameters``.
        display_name: Field label in the editor.
        type: Input widget kind.
        default: Value used if the user didn't set one.
        required: Enforced by the server on save.
        description: Helper text under the field.
        options: For ``options`` / ``multi_options``.
        display_options: Conditional visibility.
        placeholder: Placeholder text.
        type_options: Type-specific extras (``password``, ``rows``, ``min``, ``max``).
    """

    name: str
    display_name: str
    type: PropertyType
    default: Any = None
    required: bool = False
    description: str | None = None
    options: list[PropertyOption] | None = None
    display_options: DisplayOptions | None = None
    placeholder: str | None = None
    type_options: dict[str, Any] | None = None


@dataclass(frozen=True)
class CredentialSlot:
    """A credential requirement declared by a node.

    Attributes:
        name: Slot name — used as the key in ``Node.credentials``.
        credential_types: Allowed credential type slugs (``"weftlyflow.bearer_token"`` etc.).
        required: If True, the user must attach a credential to save the workflow.
        display_options: Optional conditional visibility.
    """

    name: str
    credential_types: list[str]
    required: bool = True
    display_options: DisplayOptions | None = None


@dataclass(frozen=True)
class NodeSpec:
    """Declarative description of a node implementation.

    Attributes:
        type: Unique registry key (``"weftlyflow.http_request"``).
        version: Class version. Multiple versions of the same ``type`` may coexist.
        display_name: Label shown in the palette.
        description: One-line purpose for tooltips.
        icon: Path to an SVG (relative to the node's package).
        category: Top-level UI grouping.
        group: Sub-tags (``["transform", "utility"]``) for searching.
        inputs: Input ports.
        outputs: Output ports.
        credentials: Declared credential slots.
        properties: Parameter form schema.
        supports_binary: True if the node reads/writes binary item attachments.
        documentation_url: Optional external doc link.
    """

    type: str
    version: int
    display_name: str
    description: str
    icon: str
    category: NodeCategory
    group: list[str] = field(default_factory=list)
    inputs: list[Port] = field(default_factory=lambda: [Port(name="main")])
    outputs: list[Port] = field(default_factory=lambda: [Port(name="main")])
    credentials: list[CredentialSlot] = field(default_factory=list)
    properties: list[PropertySchema] = field(default_factory=list)
    supports_binary: bool = False
    documentation_url: str | None = None
