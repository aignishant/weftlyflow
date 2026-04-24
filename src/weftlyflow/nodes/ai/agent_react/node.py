"""Agent ReAct node - one LLM turn with tool-call fan-out.

Composes an LLM call with tool-call parsing into a single node so
users can build ReAct-style agents without wiring an llm + dispatcher
pair for every turn. The node does **not** drive the full multi-turn
loop internally; loop orchestration stays in the workflow graph so
every turn is observable in the execution timeline and tool-execution
latency is bounded by individual node runs rather than one opaque
node.

Input item shape (both fields optional)::

    {"history": [{"role": "user", "content": "..."}],
     "tools":   [{"name": "...", "description": "...",
                  "parameters": {...JSON schema...}}]}

Output ports:

* ``final`` - emitted when the LLM returns no tool calls, carrying
  ``{content, history}`` where ``history`` has the assistant's reply
  appended.
* ``calls`` - emitted when tool calls are present; one item per call
  with ``{tool_name, tool_args, tool_call_id, call_index, call_total,
  history}``. The ``history`` on every call-item includes the
  assistant's tool-use message so the caller can pair it with
  :class:`weftlyflow.nodes.ai.agent_tool_result.AgentToolResultNode`
  output and feed the combined history back into another ``agent_react``
  invocation.

The ``weftlyflow.openai_api`` and ``weftlyflow.anthropic_api``
credentials are both accepted on the ``llm_api`` slot; the provider
shape is inferred from the credential slug unless ``provider`` is
explicitly overridden.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.domain.workflow import Port
from weftlyflow.nodes.ai.agent_react.providers import (
    PROVIDER_ANTHROPIC,
    PROVIDER_OPENAI,
    SUPPORTED_PROVIDERS,
    ProviderRequest,
    Turn,
    build_request,
    parse_turn,
    provider_for_slug,
)
from weftlyflow.nodes.base import BaseNode

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "llm_api"
_CREDENTIAL_SLUGS: tuple[str, ...] = (
    "weftlyflow.openai_api",
    "weftlyflow.anthropic_api",
)
_PROVIDER_AUTO: str = "auto"
_DEFAULT_HISTORY_FIELD: str = "history"
_DEFAULT_TOOLS_FIELD: str = "tools"
_DEFAULT_TIMEOUT_SECONDS: float = 120.0

log = structlog.get_logger(__name__)


class AgentReactNode(BaseNode):
    """Issue one ReAct LLM turn and fan out tool calls."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.agent_react",
        version=1,
        display_name="Agent: ReAct",
        description=(
            "One LLM turn with tool-call fan-out. Emits 'final' when "
            "the model returns a plain answer, 'calls' otherwise."
        ),
        icon="icons/agent-react.svg",
        category=NodeCategory.AI,
        group=["ai", "agent"],
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        inputs=[Port(name="main")],
        outputs=[Port(name="final"), Port(name="calls")],
        properties=[
            PropertySchema(
                name="provider",
                display_name="Provider",
                type="options",
                default=_PROVIDER_AUTO,
                options=[
                    PropertyOption(value=_PROVIDER_AUTO, label="Auto (from credential)"),
                    PropertyOption(value=PROVIDER_OPENAI, label="OpenAI"),
                    PropertyOption(value=PROVIDER_ANTHROPIC, label="Anthropic"),
                ],
            ),
            PropertySchema(
                name="model",
                display_name="Model",
                type="string",
                required=True,
                description=(
                    "Provider-native model ID "
                    "(e.g. gpt-4o-mini, claude-3-5-sonnet-latest)."
                ),
            ),
            PropertySchema(
                name="history_field",
                display_name="History Field",
                type="string",
                default=_DEFAULT_HISTORY_FIELD,
                description="JSON key on the input item holding the message list.",
            ),
            PropertySchema(
                name="tools_field",
                display_name="Tools Field",
                type="string",
                default=_DEFAULT_TOOLS_FIELD,
                description=(
                    "JSON key holding neutral tool definitions "
                    "({name, description, parameters})."
                ),
            ),
            PropertySchema(
                name="system",
                display_name="System Prompt",
                type="string",
                description="Optional system prompt; ignored when the history already has one.",
            ),
            PropertySchema(
                name="temperature",
                display_name="Temperature",
                type="number",
            ),
            PropertySchema(
                name="max_tokens",
                display_name="Max Tokens",
                type="number",
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one LLM turn per input item and split final vs. call outputs."""
        injector, payload, default_provider = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        finals: list[Item] = []
        calls: list[Item] = []
        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT_SECONDS) as client:
            for item in seed:
                final_items, call_items = await _run_turn(
                    ctx,
                    item,
                    client=client,
                    injector=injector,
                    creds=payload,
                    default_provider=default_provider,
                    logger=bound,
                )
                finals.extend(final_items)
                calls.extend(call_items)
        return [finals, calls]


async def _resolve_credentials(
    ctx: ExecutionContext,
) -> tuple[Any, dict[str, Any], str]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Agent ReAct: an llm_api credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    api_key = str(payload.get("api_key") or "").strip()
    if not api_key:
        msg = "Agent ReAct: credential has an empty 'api_key'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    slug = getattr(injector, "slug", "")
    provider = provider_for_slug(slug)
    if provider is None:
        msg = (
            f"Agent ReAct: credential type {slug!r} is not a supported "
            f"LLM provider (expected one of {sorted(_CREDENTIAL_SLUGS)})"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload, provider


async def _run_turn(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    default_provider: str,
    logger: Any,
) -> tuple[list[Item], list[Item]]:
    params = ctx.resolved_params(item=item)
    provider = _resolve_provider(params, default=default_provider, ctx=ctx)
    model = str(params.get("model") or "").strip()
    if not model:
        msg = "Agent ReAct: 'model' is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)

    history_field = str(params.get("history_field") or _DEFAULT_HISTORY_FIELD)
    tools_field = str(params.get("tools_field") or _DEFAULT_TOOLS_FIELD)
    source = item.json if isinstance(item.json, dict) else {}
    history = _coerce_history(source.get(history_field), ctx=ctx)
    tools = _coerce_tools(source.get(tools_field), ctx=ctx)
    system = str(params.get("system") or "").strip()
    temperature = _coerce_optional_float(params.get("temperature"), ctx, field="temperature")
    max_tokens = _coerce_optional_positive_int(
        params.get("max_tokens"), ctx, field="max_tokens",
    )

    try:
        req = build_request(
            provider,
            history=history,
            tools=tools,
            model=model,
            system=system,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except ValueError as exc:
        raise NodeExecutionError(
            f"Agent ReAct: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc

    response_payload = await _issue_llm_call(
        ctx,
        req=req,
        client=client,
        injector=injector,
        creds=creds,
        provider=provider,
        logger=logger,
    )

    try:
        turn = parse_turn(provider, response_payload)
    except ValueError as exc:
        raise NodeExecutionError(
            f"Agent ReAct: {exc}", node_id=ctx.node.id, original=exc,
        ) from exc

    updated_history = (
        [*history, turn.assistant_message]
        if turn.assistant_message
        else list(history)
    )

    if not turn.tool_calls:
        logger.info("agent_react.final", provider=provider)
        return ([_final_item(item, turn, updated_history)], [])
    logger.info(
        "agent_react.calls", provider=provider, count=len(turn.tool_calls),
    )
    return ([], _call_items(item, turn, updated_history))


def _resolve_provider(
    params: dict[str, Any], *, default: str, ctx: ExecutionContext,
) -> str:
    raw = str(params.get("provider") or _PROVIDER_AUTO).strip()
    if raw == _PROVIDER_AUTO or not raw:
        return default
    if raw not in SUPPORTED_PROVIDERS:
        msg = f"Agent ReAct: unsupported provider {raw!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return raw


async def _issue_llm_call(
    ctx: ExecutionContext,
    *,
    req: ProviderRequest,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    provider: str,
    logger: Any,
) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    request = client.build_request(
        "POST",
        f"{req.base_url}{req.path}",
        json=req.body,
        headers=headers,
    )
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("agent_react.request_failed", provider=provider, error=str(exc))
        msg = f"Agent ReAct: network error on {provider}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    payload = _safe_json(response)
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(payload, response.status_code)
        logger.warning(
            "agent_react.api_error",
            provider=provider,
            status=response.status_code,
            error=error,
        )
        msg = (
            f"Agent ReAct {provider} failed "
            f"(HTTP {response.status_code}): {error}"
        )
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    if not isinstance(payload, dict):
        msg = "Agent ReAct: malformed response (expected JSON object)"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return payload


def _coerce_history(
    raw: Any, *, ctx: ExecutionContext,
) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list):
        msg = "Agent ReAct: 'history' must be a list of messages"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Agent ReAct: every history entry must be an object"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(dict(entry))
    return out


def _coerce_tools(raw: Any, *, ctx: ExecutionContext) -> list[dict[str, Any]]:
    if raw is None or raw == "":
        return []
    if not isinstance(raw, list):
        msg = "Agent ReAct: 'tools' must be a list"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    out: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            msg = "Agent ReAct: every tool definition must be an object"
            raise NodeExecutionError(msg, node_id=ctx.node.id)
        out.append(dict(entry))
    return out


def _coerce_optional_float(
    raw: Any, ctx: ExecutionContext, *, field: str,
) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Agent ReAct: {field!r} must be numeric"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc


def _coerce_optional_positive_int(
    raw: Any, ctx: ExecutionContext, *, field: str,
) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        msg = f"Agent ReAct: {field!r} must be an integer"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    if value < 1:
        msg = f"Agent ReAct: {field!r} must be >= 1"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return value


def _final_item(
    source: Item, turn: Turn, history: list[dict[str, Any]],
) -> Item:
    return Item(
        json={"content": turn.content, "history": history},
        binary=source.binary,
        paired_item=source.paired_item,
        error=source.error,
    )


def _call_items(
    source: Item, turn: Turn, history: list[dict[str, Any]],
) -> list[Item]:
    total = len(turn.tool_calls)
    return [
        Item(
            json={
                "tool_name": call.tool_name,
                "tool_args": call.tool_args,
                "tool_call_id": call.tool_call_id,
                "call_index": idx,
                "call_total": total,
                "history": history,
            },
            binary=source.binary,
            paired_item=source.paired_item,
            error=source.error,
        )
        for idx, call in enumerate(turn.tool_calls)
    ]


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(payload: Any, status_code: int) -> str:
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
            err_type = error.get("type")
            if isinstance(err_type, str) and err_type:
                return err_type
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return f"HTTP {status_code}"
