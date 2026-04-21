"""NodeSpec → catalog DTO mapper."""

from __future__ import annotations

from typing import TYPE_CHECKING

from weftlyflow.server.schemas.node_types import (
    NodeTypeResponse,
    PropertyOptionDTO,
    PropertySchemaDTO,
)

if TYPE_CHECKING:
    from weftlyflow.domain.node_spec import NodeSpec, PropertyOption, PropertySchema


def node_spec_to_response(spec: NodeSpec) -> NodeTypeResponse:
    """Project a :class:`NodeSpec` onto the catalog wire format."""
    return NodeTypeResponse(
        type=spec.type,
        version=spec.version,
        display_name=spec.display_name,
        description=spec.description,
        icon=spec.icon,
        category=spec.category.value,
        group=list(spec.group),
        supports_binary=spec.supports_binary,
        properties=[_property_to_dto(p) for p in spec.properties],
    )


def _property_to_dto(prop: PropertySchema) -> PropertySchemaDTO:
    return PropertySchemaDTO(
        name=prop.name,
        display_name=prop.display_name,
        type=prop.type,
        default=prop.default,
        required=prop.required,
        description=prop.description,
        options=[_option_to_dto(o) for o in prop.options] if prop.options is not None else None,
        placeholder=prop.placeholder,
        type_options=dict(prop.type_options) if prop.type_options is not None else None,
    )


def _option_to_dto(opt: PropertyOption) -> PropertyOptionDTO:
    return PropertyOptionDTO(value=opt.value, label=opt.label, description=opt.description)
