"""Unit tests for :class:`PushoverNode`.

Exercises every supported operation against a respx-mocked Pushover
API. Verifies the distinctive form-body auth scheme where the app
``token`` and recipient ``user`` key travel as form fields inside the
``application/x-www-form-urlencoded`` POST body (no ``Authorization``
header is ever sent), the character-cap enforcement, the
emergency-priority ``retry``/``expire`` requirements, and the Pushover
``status != 1`` failure surfacing.
"""

from __future__ import annotations

from urllib.parse import parse_qs

import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import PushoverApiCredential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.pushover import PushoverNode
from weftlyflow.nodes.integrations.pushover.constants import API_BASE_URL
from weftlyflow.nodes.integrations.pushover.operations import build_request

_CRED_ID: str = "cr_po"
_PROJECT_ID: str = "pr_test"
_APP_TOKEN: str = "app-token-123"
_USER_KEY: str = "user-key-456"


def _resolver(
    *,
    app_token: str = _APP_TOKEN,
    user_key: str = _USER_KEY,
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.pushover_api": PushoverApiCredential},
        rows={
            _CRED_ID: (
                "weftlyflow.pushover_api",
                {"app_token": app_token, "user_key": user_key},
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    inputs: list[Item] | None = None,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": list(inputs or [])},
        credential_resolver=resolver,
    )


def _form(request_content: bytes) -> dict[str, list[str]]:
    return parse_qs(request_content.decode("ascii"))


# --- send_notification -------------------------------------------------


@respx.mock
async def test_send_notification_embeds_token_and_user_in_form_body() -> None:
    route = respx.post(f"{API_BASE_URL}/messages.json").mock(
        return_value=Response(200, json={"status": 1, "request": "r1"}),
    )
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={
            "operation": "send_notification",
            "message": "Deploy succeeded",
            "title": "Deploy",
            "url": "https://example.com/build/42",
            "url_title": "View build",
        },
        credentials={"pushover_api": _CRED_ID},
    )
    await PushoverNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    request = route.calls.last.request
    # Pushover carries credentials in the body — no Authorization header.
    assert "authorization" not in {k.lower() for k in request.headers}
    form = _form(request.content)
    assert form["token"] == [_APP_TOKEN]
    assert form["user"] == [_USER_KEY]
    assert form["message"] == ["Deploy succeeded"]
    assert form["title"] == ["Deploy"]
    assert form["url"] == ["https://example.com/build/42"]
    assert form["url_title"] == ["View build"]


@respx.mock
async def test_emergency_priority_sends_retry_and_expire() -> None:
    route = respx.post(f"{API_BASE_URL}/messages.json").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={
            "operation": "send_notification",
            "message": "Page oncall",
            "priority": 2,
            "retry": 60,
            "expire": 3600,
        },
        credentials={"pushover_api": _CRED_ID},
    )
    await PushoverNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    form = _form(route.calls.last.request.content)
    assert form["priority"] == ["2"]
    assert form["retry"] == ["60"]
    assert form["expire"] == ["3600"]


def test_emergency_priority_requires_retry() -> None:
    with pytest.raises(ValueError, match="'retry'"):
        build_request(
            "send_notification",
            {"message": "x", "priority": 2, "expire": 3600},
        )


def test_emergency_priority_requires_expire() -> None:
    with pytest.raises(ValueError, match="'expire'"):
        build_request(
            "send_notification",
            {"message": "x", "priority": 2, "retry": 60},
        )


def test_message_too_long_raises() -> None:
    with pytest.raises(ValueError, match="exceeds 1024"):
        build_request("send_notification", {"message": "a" * 1025})


def test_priority_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="in \\[-2, 2\\]"):
        build_request(
            "send_notification",
            {"message": "x", "priority": 5},
        )


# --- send_glance -------------------------------------------------------


@respx.mock
async def test_send_glance_posts_glance_path_with_subset_fields() -> None:
    route = respx.post(f"{API_BASE_URL}/glances.json").mock(
        return_value=Response(200, json={"status": 1}),
    )
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={
            "operation": "send_glance",
            "text": "42 open",
            "subtext": "SLO: 99.9",
            "count": 42,
            "percent": 87,
        },
        credentials={"pushover_api": _CRED_ID},
    )
    await PushoverNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])
    form = _form(route.calls.last.request.content)
    assert form["token"] == [_APP_TOKEN]
    assert form["user"] == [_USER_KEY]
    assert form["text"] == ["42 open"]
    assert form["count"] == ["42"]
    assert form["percent"] == ["87"]


def test_send_glance_rejects_percent_out_of_range() -> None:
    with pytest.raises(ValueError, match="in \\[0, 100\\]"):
        build_request("send_glance", {"percent": 150})


def test_send_glance_requires_at_least_one_field() -> None:
    with pytest.raises(ValueError, match="at least one updatable field"):
        build_request("send_glance", {})


# --- errors / credentials ----------------------------------------------


@respx.mock
async def test_pushover_status_zero_raises_node_execution_error() -> None:
    respx.post(f"{API_BASE_URL}/messages.json").mock(
        return_value=Response(
            200,
            json={"status": 0, "errors": ["message cannot be blank"]},
        ),
    )
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={"operation": "send_notification", "message": "ok"},
        credentials={"pushover_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="message cannot be blank"):
        await PushoverNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


@respx.mock
async def test_http_error_surfaces_errors_list() -> None:
    respx.post(f"{API_BASE_URL}/messages.json").mock(
        return_value=Response(
            400,
            json={"status": 0, "errors": ["application token is invalid"]},
        ),
    )
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={"operation": "send_notification", "message": "ok"},
        credentials={"pushover_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="application token is invalid"):
        await PushoverNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={"operation": "send_notification", "message": "x"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await PushoverNode().execute(_ctx_for(node, resolver=_resolver()), [Item()])


async def test_empty_app_token_raises() -> None:
    node = Node(
        id="node_1",
        name="Pushover",
        type="weftlyflow.pushover",
        parameters={"operation": "send_notification", "message": "x"},
        credentials={"pushover_api": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="app_token"):
        await PushoverNode().execute(
            _ctx_for(node, resolver=_resolver(app_token="")), [Item()],
        )


# --- direct builder unit tests -----------------------------------------


def test_build_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("broadcast_everything", {})
