"""HTML Parse node — run CSS selectors over each item's HTML payload.

Each ``extraction`` entry runs a CSS selector against the HTML source and
writes the extracted value to a dotted path on the output item. Supported
return kinds:

* ``text`` — the element's concatenated inner text (default).
* ``html`` — the element's serialized inner HTML.
* ``attribute`` — the value of ``attribute_name`` on the element.

When ``return_all`` is True the result is a list (one entry per matched
element), otherwise the first match is returned (or ``None`` when no
element matches).

Input source defaults to the item's ``html`` field, but any dotted path on
the item can be used via ``source_path``. When ``source_path`` resolves to
something other than a string, the node raises a :class:`ValueError`
describing the offending item.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal

from bs4 import BeautifulSoup

from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    NodeCategory,
    NodeSpec,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.utils import get_path, set_path

_DEFAULT_SOURCE_PATH: str = "html"
_DEFAULT_PARSER: str = "html.parser"
_RETURN_TEXT: str = "text"
_RETURN_HTML: str = "html"
_RETURN_ATTRIBUTE: str = "attribute"
_RETURN_KINDS: tuple[str, ...] = (_RETURN_TEXT, _RETURN_HTML, _RETURN_ATTRIBUTE)

ReturnKind = Literal["text", "html", "attribute"]


class HtmlParseNode(BaseNode):
    """Extract values from HTML using CSS selectors."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.html_parse",
        version=1,
        display_name="HTML Parse",
        description="Extract values from HTML using CSS selectors.",
        icon="icons/html-parse.svg",
        category=NodeCategory.CORE,
        group=["transform"],
        inputs=[Port(name="main")],
        outputs=[Port(name="main")],
        properties=[
            PropertySchema(
                name="source_path",
                display_name="HTML source path",
                type="string",
                default=_DEFAULT_SOURCE_PATH,
                description="Dotted path in the item that holds the HTML string.",
            ),
            PropertySchema(
                name="extractions",
                display_name="Extractions",
                type="fixed_collection",
                default=[],
                description=(
                    'List of `{"name": "title", "selector": "h1", '
                    '"return": "text", "return_all": false, "attribute_name": ""}`.'
                ),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Apply every extraction to each item's HTML and emit enriched items."""
        source_path = str(ctx.param("source_path", _DEFAULT_SOURCE_PATH)).strip()
        extractions = _coerce_extractions(ctx.param("extractions", []))
        out: list[Item] = [
            _extract_one(item, source_path=source_path, extractions=extractions)
            for item in items
        ]
        return [out]


def _extract_one(
    item: Item,
    *,
    source_path: str,
    extractions: list[dict[str, Any]],
) -> Item:
    payload: dict[str, Any] = _deep_copy_json(item.json)
    if not extractions:
        return Item(
            json=payload,
            binary=dict(item.binary),
            paired_item=list(item.paired_item),
            error=item.error,
        )
    raw = get_path(payload, source_path)
    if not isinstance(raw, str):
        msg = f"HTML Parse: source at {source_path!r} is not a string"
        raise ValueError(msg)
    soup = BeautifulSoup(raw, _DEFAULT_PARSER)
    for entry in extractions:
        value = _run_extraction(soup, entry)
        set_path(payload, entry["name"], value)
    return Item(
        json=payload,
        binary=dict(item.binary),
        paired_item=list(item.paired_item),
        error=item.error,
    )


def _run_extraction(soup: BeautifulSoup, entry: dict[str, Any]) -> Any:
    selector: str = entry["selector"]
    kind: ReturnKind = entry["return"]
    return_all: bool = entry["return_all"]
    attribute_name: str = entry["attribute_name"]

    matches = soup.select(selector) if return_all else (
        [soup.select_one(selector)] if soup.select_one(selector) is not None else []
    )
    values = [_tag_value(tag, kind=kind, attribute_name=attribute_name) for tag in matches]
    if return_all:
        return values
    return values[0] if values else None


def _tag_value(tag: Any, *, kind: ReturnKind, attribute_name: str) -> Any:
    if kind == _RETURN_HTML:
        return tag.decode_contents()
    if kind == _RETURN_ATTRIBUTE:
        return tag.get(attribute_name)
    return tag.get_text(" ", strip=True)


def _coerce_extractions(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        selector = entry.get("selector")
        if not isinstance(name, str) or not name:
            continue
        if not isinstance(selector, str) or not selector:
            continue
        kind_raw = entry.get("return", _RETURN_TEXT)
        kind = kind_raw if kind_raw in _RETURN_KINDS else _RETURN_TEXT
        attribute_name = entry.get("attribute_name", "")
        if kind == _RETURN_ATTRIBUTE and not (
            isinstance(attribute_name, str) and attribute_name
        ):
            msg = f"HTML Parse: extraction {name!r} needs 'attribute_name' for 'attribute' return"
            raise ValueError(msg)
        result.append(
            {
                "name": name,
                "selector": selector,
                "return": kind,
                "return_all": bool(entry.get("return_all", False)),
                "attribute_name": str(attribute_name or ""),
            },
        )
    return result


def _deep_copy_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _deep_copy_json(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_deep_copy_json(item) for item in value]
    return value
