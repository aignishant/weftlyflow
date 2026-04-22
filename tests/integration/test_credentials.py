"""Phase-4 integration — credentials CRUD + HTTP Request uses them end-to-end.

Touches every part of the credential stack that's exposed over HTTP:

* ``POST /api/v1/credentials`` encrypts + stores.
* ``GET /api/v1/credentials`` lists metadata only.
* ``POST /api/v1/credentials/{id}/test`` runs the credential-type test.
* ``POST /api/v1/workflows/{id}/execute`` runs a workflow whose HTTP Request
  node uses an expression in its URL and a real stored credential — the
  outbound call is mocked via :mod:`respx`.

No real network is involved.
"""

from __future__ import annotations

import pytest
import respx
from httpx import AsyncClient, Response

pytestmark = pytest.mark.integration


async def test_credential_crud_no_plaintext_in_response(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    create = await client.post(
        "/api/v1/credentials",
        headers=auth_headers,
        json={
            "name": "github-token",
            "type": "weftlyflow.bearer_token",
            "data": {"token": "ghp_real_secret"},
        },
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["name"] == "github-token"
    assert body["type"] == "weftlyflow.bearer_token"
    # Secret must never appear in the response body.
    assert "token" not in body
    assert "ghp_real_secret" not in create.text

    listing = await client.get("/api/v1/credentials", headers=auth_headers)
    assert listing.status_code == 200
    assert [r["id"] for r in listing.json()] == [body["id"]]

    test = await client.post(
        f"/api/v1/credentials/{body['id']}/test", headers=auth_headers,
    )
    assert test.status_code == 200
    assert test.json()["ok"] is True

    deleted = await client.delete(
        f"/api/v1/credentials/{body['id']}", headers=auth_headers,
    )
    assert deleted.status_code == 204


async def test_credential_types_catalog(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.get("/api/v1/credential-types", headers=auth_headers)
    assert resp.status_code == 200
    slugs = {row["slug"] for row in resp.json()}
    assert slugs == {
        "weftlyflow.bearer_token",
        "weftlyflow.basic_auth",
        "weftlyflow.api_key_header",
        "weftlyflow.api_key_query",
        "weftlyflow.oauth2_generic",
    }


async def test_invalid_credential_type_rejected(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    resp = await client.post(
        "/api/v1/credentials",
        headers=auth_headers,
        json={"name": "bad", "type": "weftlyflow.nonexistent", "data": {}},
    )
    assert resp.status_code == 400


@respx.mock
async def test_http_request_node_uses_expression_and_credential(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    route = respx.get("https://api.example.com/items/123").mock(
        return_value=Response(200, json={"id": 123, "name": "widget"}),
    )

    # 1. Create a credential.
    cred_resp = await client.post(
        "/api/v1/credentials",
        headers=auth_headers,
        json={
            "name": "api-bearer",
            "type": "weftlyflow.bearer_token",
            "data": {"token": "my-secret-token"},
        },
    )
    credential_id = cred_resp.json()["id"]

    # 2. Build a workflow with an HTTP Request node wired to the credential.
    wf_resp = await client.post(
        "/api/v1/workflows",
        headers=auth_headers,
        json={
            "name": "http-demo",
            "nodes": [
                {"id": "node_trigger", "name": "Trigger", "type": "weftlyflow.manual_trigger"},
                {
                    "id": "node_http",
                    "name": "HTTP",
                    "type": "weftlyflow.http_request",
                    "parameters": {
                        "url": "https://api.example.com/items/{{ $json.id }}",
                        "method": "GET",
                    },
                    "credentials": {"auth": credential_id},
                },
            ],
            "connections": [
                {"source_node": "node_trigger", "target_node": "node_http"},
            ],
        },
    )
    wf_id = wf_resp.json()["id"]

    # 3. Execute with an item carrying id=123.
    exec_resp = await client.post(
        f"/api/v1/workflows/{wf_id}/execute",
        headers=auth_headers,
        json={"initial_items": [{"id": 123}]},
    )
    assert exec_resp.status_code == 200, exec_resp.text
    body = exec_resp.json()
    assert body["status"] == "success"

    # 4. The outbound call got the expression-resolved URL + bearer token.
    assert route.called
    sent = route.calls.last.request
    assert sent.headers["authorization"] == "Bearer my-secret-token"
    # Run-data carries the parsed response.
    http_out = body["run_data"]["node_http"][0]["items"][0][0]
    assert http_out["status_code"] == 200
    assert http_out["body"] == {"id": 123, "name": "widget"}
