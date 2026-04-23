"""Unit tests for :class:`RedditNode` and ``RedditOAuth2Credential``.

Reddit is the catalog's first integration that **enforces** a
platform-specific User-Agent format alongside Bearer auth. The
credential assembles ``platform:app_id:version (by /u/username)`` on
every inject — a generic httpx default would be throttled server-side.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from httpx import Response

from tests.unit.engine.conftest import build_workflow
from weftlyflow.credentials.resolver import InMemoryCredentialResolver
from weftlyflow.credentials.types import RedditOAuth2Credential
from weftlyflow.domain.errors import NodeExecutionError
from weftlyflow.domain.execution import Item
from weftlyflow.domain.workflow import Node
from weftlyflow.engine.context import ExecutionContext
from weftlyflow.nodes.integrations.reddit import RedditNode
from weftlyflow.nodes.integrations.reddit.operations import build_request

_CRED_ID: str = "cr_reddit"
_PROJECT_ID: str = "pr_test"
_TOKEN: str = "reddit_tkn_abc"
_API: str = "https://oauth.reddit.com"
_UA: str = "linux:weftlyflow:1.0.0 (by /u/nishant)"


def _resolver(
    *,
    token: str = _TOKEN,
    platform: str = "linux",
    app_id: str = "weftlyflow",
    version: str = "1.0.0",
    username: str = "nishant",
) -> InMemoryCredentialResolver:
    return InMemoryCredentialResolver(
        types={"weftlyflow.reddit_oauth2": RedditOAuth2Credential},
        rows={
            _CRED_ID: (
                "weftlyflow.reddit_oauth2",
                {
                    "access_token": token,
                    "platform": platform,
                    "app_id": app_id,
                    "version": version,
                    "username": username,
                },
                _PROJECT_ID,
            ),
        },
    )


def _ctx_for(
    node: Node,
    *,
    resolver: InMemoryCredentialResolver | None = None,
) -> ExecutionContext:
    wf = build_workflow([node], [], project_id=_PROJECT_ID)
    return ExecutionContext(
        workflow=wf,
        execution_id="ex_test",
        mode="manual",
        node=node,
        inputs={"main": []},
        credential_resolver=resolver or _resolver(),
    )


# --- credential: Bearer + platform-formatted User-Agent -----------


async def test_credential_inject_sets_bearer_and_formatted_user_agent() -> None:
    request = httpx.Request("GET", f"{_API}/api/v1/me")
    out = await RedditOAuth2Credential().inject(
        {
            "access_token": _TOKEN,
            "platform": "linux",
            "app_id": "weftlyflow",
            "version": "1.0.0",
            "username": "nishant",
        },
        request,
    )
    assert out.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert out.headers["User-Agent"] == _UA


async def test_credential_user_agent_omits_suffix_when_username_blank() -> None:
    request = httpx.Request("GET", f"{_API}/api/v1/me")
    out = await RedditOAuth2Credential().inject(
        {
            "access_token": _TOKEN,
            "platform": "web",
            "app_id": "weftlyflow",
            "version": "1.0.0",
            "username": "",
        },
        request,
    )
    assert out.headers["User-Agent"] == "web:weftlyflow:1.0.0"


# --- get_me --------------------------------------------------------


@respx.mock
async def test_get_me_sends_bearer_and_user_agent() -> None:
    route = respx.get(f"{_API}/api/v1/me").mock(
        return_value=Response(200, json={"name": "nishant"}),
    )
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={"operation": "get_me"},
        credentials={"reddit_oauth2": _CRED_ID},
    )
    await RedditNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == f"Bearer {_TOKEN}"
    assert sent.headers["User-Agent"] == _UA


# --- submit_post (form-encoded) -----------------------------------


@respx.mock
async def test_submit_post_self_uses_form_encoding_and_text_body() -> None:
    route = respx.post(f"{_API}/api/submit").mock(
        return_value=Response(200, json={"json": {"data": {"id": "abc"}}}),
    )
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={
            "operation": "submit_post",
            "subreddit": "test",
            "title": "Hello",
            "kind": "self",
            "text": "Body text",
        },
        credentials={"reddit_oauth2": _CRED_ID},
    )
    await RedditNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
    body = sent.content.decode()
    assert "sr=test" in body
    assert "title=Hello" in body
    assert "kind=self" in body
    assert "text=Body+text" in body


@respx.mock
async def test_submit_post_link_includes_url() -> None:
    route = respx.post(f"{_API}/api/submit").mock(
        return_value=Response(200, json={"json": {"data": {"id": "abc"}}}),
    )
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={
            "operation": "submit_post",
            "subreddit": "test",
            "title": "Hello",
            "kind": "link",
            "url": "https://example.com",
        },
        credentials={"reddit_oauth2": _CRED_ID},
    )
    await RedditNode().execute(_ctx_for(node), [Item()])
    body = route.calls.last.request.content.decode()
    assert "kind=link" in body
    assert "url=https%3A%2F%2Fexample.com" in body


def test_submit_post_link_requires_url() -> None:
    with pytest.raises(ValueError, match="'url' is required"):
        build_request(
            "submit_post",
            {"subreddit": "test", "title": "Hello", "kind": "link"},
        )


def test_submit_post_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="'kind' must be"):
        build_request(
            "submit_post",
            {"subreddit": "test", "title": "Hello", "kind": "video"},
        )


def test_submit_post_requires_subreddit_and_title() -> None:
    with pytest.raises(ValueError, match="'subreddit' is required"):
        build_request("submit_post", {"title": "X"})
    with pytest.raises(ValueError, match="'title' is required"):
        build_request("submit_post", {"subreddit": "test"})


# --- get_subreddit -------------------------------------------------


@respx.mock
async def test_get_subreddit_uses_subreddit_in_path() -> None:
    route = respx.get(f"{_API}/r/python/about").mock(
        return_value=Response(200, json={"data": {"display_name": "python"}}),
    )
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={"operation": "get_subreddit", "subreddit": "python"},
        credentials={"reddit_oauth2": _CRED_ID},
    )
    await RedditNode().execute(_ctx_for(node), [Item()])
    assert route.called


# --- list_hot ------------------------------------------------------


@respx.mock
async def test_list_hot_forwards_limit_and_after() -> None:
    route = respx.get(f"{_API}/r/python/hot").mock(
        return_value=Response(200, json={"data": {"children": []}}),
    )
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={
            "operation": "list_hot",
            "subreddit": "python",
            "limit": 25,
            "after": "t3_xyz",
        },
        credentials={"reddit_oauth2": _CRED_ID},
    )
    await RedditNode().execute(_ctx_for(node), [Item()])
    sent = route.calls.last.request
    assert sent.url.params["limit"] == "25"
    assert sent.url.params["after"] == "t3_xyz"


# --- errors --------------------------------------------------------


@respx.mock
async def test_api_error_parses_reddit_json_errors_array() -> None:
    respx.post(f"{_API}/api/submit").mock(
        return_value=Response(
            400,
            json={
                "json": {
                    "errors": [
                        ["SUBREDDIT_NOEXIST", "that subreddit doesn't exist", "sr"],
                    ],
                },
            },
        ),
    )
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={
            "operation": "submit_post",
            "subreddit": "doesnotexist",
            "title": "Hi",
            "kind": "self",
        },
        credentials={"reddit_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="that subreddit doesn't exist"):
        await RedditNode().execute(_ctx_for(node), [Item()])


async def test_missing_credential_raises() -> None:
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={"operation": "get_me"},
    )
    with pytest.raises(NodeExecutionError, match="credential is required"):
        await RedditNode().execute(_ctx_for(node), [Item()])


async def test_empty_access_token_raises() -> None:
    resolver = _resolver(token="")
    node = Node(
        id="node_1",
        name="Reddit",
        type="weftlyflow.reddit",
        parameters={"operation": "get_me"},
        credentials={"reddit_oauth2": _CRED_ID},
    )
    with pytest.raises(NodeExecutionError, match="empty 'access_token'"):
        await RedditNode().execute(_ctx_for(node, resolver=resolver), [Item()])


def test_unknown_operation_raises() -> None:
    with pytest.raises(ValueError, match="unsupported operation"):
        build_request("nuke", {})
