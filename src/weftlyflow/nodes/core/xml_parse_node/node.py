"""XML Parse node — convert XML text into JSON-shaped dicts.

For each input item the node reads an XML string from ``source_path`` and
writes a recursive dict representation to ``destination_path``. The
transformation is deliberately opinionated so downstream nodes see a
predictable shape:

* Each element becomes ``{"tag": str, "attrs": dict, "text": str | None,
  "children": list[dict]}``.
* Attributes are preserved verbatim; values remain strings (XML has no
  type system).
* Whitespace-only text is collapsed to ``None`` so empty elements read
  naturally.

Parsing uses :mod:`defusedxml.ElementTree` to neutralise billion-laughs,
entity expansion, and external-entity attacks before the document ever
reaches :mod:`xml.etree`.
"""

from __future__ import annotations

from typing import Any, ClassVar

from defusedxml import ElementTree as DefusedET

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import NodeCategory, NodeSpec, PropertySchema
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import get_path, set_path

_DEFAULT_SOURCE_PATH: str = "xml"
_DEFAULT_DESTINATION_PATH: str = "parsed"


class XmlParseNode(BaseNode):
    """Parse an XML string into a dict and attach it to each item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.xml_parse",
        version=1,
        display_name="XML Parse",
        description="Convert an XML string into a JSON-shaped dict.",
        icon="icons/xml-parse.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="source_path",
                display_name="XML source path",
                type="string",
                default=_DEFAULT_SOURCE_PATH,
                description="Dotted path in the item that holds the XML string.",
            ),
            PropertySchema(
                name="destination_path",
                display_name="Destination path",
                type="string",
                default=_DEFAULT_DESTINATION_PATH,
                description="Dotted path where the parsed dict is written.",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Parse each item's XML payload and emit enriched items."""
        source_path = str(ctx.param("source_path", _DEFAULT_SOURCE_PATH)).strip()
        destination_path = str(
            ctx.param("destination_path", _DEFAULT_DESTINATION_PATH),
        ).strip()
        out = [
            _parse_one(
                item,
                source_path=source_path,
                destination_path=destination_path,
            )
            for item in items
        ]
        return [out]


def _parse_one(
    item: Item,
    *,
    source_path: str,
    destination_path: str,
) -> Item:
    payload: dict[str, Any] = _deep_copy_json(item.json)
    raw = get_path(payload, source_path)
    if not isinstance(raw, str):
        msg = f"XML Parse: source at {source_path!r} is not a string"
        raise ValueError(msg)
    try:
        root = DefusedET.fromstring(raw)
    except DefusedET.ParseError as exc:
        msg = f"XML Parse: invalid XML at {source_path!r}: {exc}"
        raise ValueError(msg) from exc
    set_path(payload, destination_path, _element_to_dict(root))
    return Item(
        json=payload,
        binary=dict(item.binary),
        paired_item=list(item.paired_item),
        error=item.error,
    )


def _element_to_dict(element: Any) -> dict[str, Any]:
    text = (element.text or "").strip()
    return {
        "tag": element.tag,
        "attrs": dict(element.attrib),
        "text": text or None,
        "children": [_element_to_dict(child) for child in element],
    }


def _deep_copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_deep_copy_json(item) for item in value]
    return value
