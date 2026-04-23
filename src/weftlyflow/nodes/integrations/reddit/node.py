"""Reddit node — authenticated user, submissions, subreddit reads.

Dispatches against ``https://oauth.reddit.com`` with Bearer auth and a
Reddit-formatted User-Agent both applied by
:class:`~weftlyflow.credentials.types.reddit_oauth2.RedditOAuth2Credential`.
The submission endpoint expects form-encoded input; the node switches
Content-Type based on the operation so the operations layer can stay
declarative.

Parameters (all expression-capable):

* ``operation`` — ``get_me`` / ``submit_post`` / ``get_subreddit`` /
  ``list_hot``.
* ``subreddit`` — subreddit name without the leading ``r/``.
* ``title`` / ``kind`` / ``url`` / ``text`` / ``nsfw`` — submit_post.
* ``limit`` / ``after`` — list_hot pagination.

Output: one item per input item with ``operation``, ``status``, and
parsed ``response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import structlog

from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.node_spec import (
    CredentialSlot,
    DisplayOptions,
    NodeCategory,
    NodeSpec,
    PropertyOption,
    PropertySchema,
)
from weftlyflow.nodes.base import BaseNode
from weftlyflow.nodes.integrations.reddit.constants import (
    API_BASE_URL,
    DEFAULT_TIMEOUT_SECONDS,
    KIND_LINK,
    KIND_SELF,
    OP_GET_ME,
    OP_GET_SUBREDDIT,
    OP_LIST_HOT,
    OP_SUBMIT_POST,
    SUPPORTED_OPERATIONS,
)
from weftlyflow.nodes.integrations.reddit.operations import build_request

if TYPE_CHECKING:
    from weftlyflow.engine.context import ExecutionContext

_CREDENTIAL_SLOT: str = "reddit_oauth2"
_CREDENTIAL_SLUGS: tuple[str, ...] = ("weftlyflow.reddit_oauth2",)
_REDDIT_ERROR_TUPLE_MIN: int = 2

log = structlog.get_logger(__name__)


class RedditNode(BaseNode):
    """Dispatch a single Reddit API call per input item."""

    spec: ClassVar[NodeSpec] = NodeSpec(
        type="weftlyflow.reddit",
        version=1,
        display_name="Reddit",
        description="Read user info, submit posts, and browse subreddits via the Reddit API.",
        icon="icons/reddit.svg",
        category=NodeCategory.INTEGRATION,
        group=["social"],
        documentation_url="https://www.reddit.com/dev/api/",
        credentials=[
            CredentialSlot(
                name=_CREDENTIAL_SLOT,
                required=True,
                credential_types=list(_CREDENTIAL_SLUGS),
            ),
        ],
        properties=[
            PropertySchema(
                name="operation",
                display_name="Operation",
                type="options",
                default=OP_GET_ME,
                required=True,
                options=[
                    PropertyOption(value=OP_GET_ME, label="Get Authenticated User"),
                    PropertyOption(value=OP_SUBMIT_POST, label="Submit Post"),
                    PropertyOption(value=OP_GET_SUBREDDIT, label="Get Subreddit"),
                    PropertyOption(value=OP_LIST_HOT, label="List Hot Posts"),
                ],
            ),
            PropertySchema(
                name="subreddit",
                display_name="Subreddit",
                type="string",
                display_options=DisplayOptions(
                    show={
                        "operation": [
                            OP_SUBMIT_POST,
                            OP_GET_SUBREDDIT,
                            OP_LIST_HOT,
                        ],
                    },
                ),
            ),
            PropertySchema(
                name="title",
                display_name="Title",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_POST]}),
            ),
            PropertySchema(
                name="kind",
                display_name="Kind",
                type="options",
                default=KIND_SELF,
                options=[
                    PropertyOption(value=KIND_SELF, label="Self (Text)"),
                    PropertyOption(value=KIND_LINK, label="Link"),
                ],
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_POST]}),
            ),
            PropertySchema(
                name="url",
                display_name="URL",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SUBMIT_POST], "kind": [KIND_LINK]},
                ),
            ),
            PropertySchema(
                name="text",
                display_name="Body (Markdown)",
                type="string",
                display_options=DisplayOptions(
                    show={"operation": [OP_SUBMIT_POST], "kind": [KIND_SELF]},
                ),
            ),
            PropertySchema(
                name="nsfw",
                display_name="NSFW",
                type="boolean",
                display_options=DisplayOptions(show={"operation": [OP_SUBMIT_POST]}),
            ),
            PropertySchema(
                name="limit",
                display_name="Limit",
                type="number",
                display_options=DisplayOptions(show={"operation": [OP_LIST_HOT]}),
            ),
            PropertySchema(
                name="after",
                display_name="After (pagination token)",
                type="string",
                display_options=DisplayOptions(show={"operation": [OP_LIST_HOT]}),
            ),
        ],
    )

    async def execute(
        self,
        ctx: ExecutionContext,
        items: list[Item],
    ) -> list[list[Item]]:
        """Issue one Reddit call per input item."""
        injector, payload = await _resolve_credentials(ctx)
        seed = items or [Item()]
        bound = log.bind(execution_id=ctx.execution_id, node_id=ctx.node.id)
        results: list[Item] = []
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            for item in seed:
                results.append(
                    await _dispatch_one(
                        ctx, item, client=client, injector=injector,
                        creds=payload, logger=bound,
                    ),
                )
        return [results]


async def _resolve_credentials(ctx: ExecutionContext) -> tuple[Any, dict[str, Any]]:
    credential = await ctx.load_credential(_CREDENTIAL_SLOT)
    if credential is None:
        msg = "Reddit: a reddit_oauth2 credential is required"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    injector, payload = credential
    if not str(payload.get("access_token") or "").strip():
        msg = "Reddit: credential has an empty 'access_token'"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    return injector, payload


async def _dispatch_one(
    ctx: ExecutionContext,
    item: Item,
    *,
    client: httpx.AsyncClient,
    injector: Any,
    creds: dict[str, Any],
    logger: Any,
) -> Item:
    params = ctx.resolved_params(item=item)
    operation = str(params.get("operation") or OP_GET_ME).strip()
    if operation not in SUPPORTED_OPERATIONS:
        msg = f"Reddit: unsupported operation {operation!r}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    try:
        method, path, body, query = build_request(operation, params)
    except ValueError as exc:
        raise NodeExecutionError(str(exc), node_id=ctx.node.id, original=exc) from exc
    request = _build_request(client, method, path, body, query, operation)
    request = await injector.inject(creds, request)
    try:
        response = await client.send(request)
    except httpx.HTTPError as exc:
        logger.error("reddit.request_failed", operation=operation, error=str(exc))
        msg = f"Reddit: network error on {operation}: {exc}"
        raise NodeExecutionError(msg, node_id=ctx.node.id, original=exc) from exc
    parsed = _safe_json(response)
    result: dict[str, Any] = {
        "operation": operation,
        "status": response.status_code,
        "response": parsed,
    }
    if response.status_code >= httpx.codes.BAD_REQUEST:
        error = _error_message(parsed, response.status_code)
        logger.warning(
            "reddit.api_error",
            operation=operation,
            status=response.status_code,
            error=error,
        )
        msg = f"Reddit {operation} failed (HTTP {response.status_code}): {error}"
        raise NodeExecutionError(msg, node_id=ctx.node.id)
    logger.info("reddit.ok", operation=operation, status=response.status_code)
    return Item(json=result)


def _build_request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    query: dict[str, Any],
    operation: str,
) -> httpx.Request:
    headers = {"Accept": "application/json"}
    if operation == OP_SUBMIT_POST and body is not None:
        return client.build_request(
            method, path, params=query or None, data=body, headers=headers,
        )
    return client.build_request(
        method, path, params=query or None, json=body, headers=headers,
    )


def _safe_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text, "status_code": response.status_code}


def _error_message(parsed: Any, status_code: int) -> str:
    if isinstance(parsed, dict):
        for key in ("message", "error", "explanation"):
            value = parsed.get(key)
            if isinstance(value, str) and value:
                return value
        # Reddit's JSON:API-style error envelope: {"json": {"errors": [[code, msg, field], ...]}}
        nested = parsed.get("json")
        if isinstance(nested, dict):
            errors = nested.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0]
                if (
                    isinstance(first, list)
                    and len(first) >= _REDDIT_ERROR_TUPLE_MIN
                    and isinstance(first[1], str)
                ):
                    return first[1]
    return f"HTTP {status_code}"
