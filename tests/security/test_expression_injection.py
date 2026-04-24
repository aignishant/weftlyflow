"""Expression-sandbox probes at the API boundary.

The expression engine ships with a dedicated bypass corpus and fuzz
suite at :mod:`tests.unit.expression`. This file exercises the same
concern one layer up — the operator-visible surface — so a regression
in, say, how the server passes expressions through to the engine gets
caught.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.security


_DANGEROUS_EXPRESSIONS: list[str] = [
    "{{ __import__('os').system('echo pwn') }}",
    "{{ (lambda: __import__('subprocess')).__call__().run(['id']) }}",
    "{{ ().__class__.__mro__[-1].__subclasses__() }}",
    "{{ open('/etc/passwd').read() }}",
]


@pytest.mark.parametrize("expression", _DANGEROUS_EXPRESSIONS)
async def test_dangerous_expression_does_not_execute(
    client: AsyncClient, auth_headers: dict[str, str], expression: str,
) -> None:
    body = {
        "name": "sandbox-probe",
        "nodes": [
            {"id": "t", "name": "Trigger", "type": "weftlyflow.manual_trigger"},
            {
                "id": "s",
                "name": "Set",
                "type": "weftlyflow.set",
                "parameters": {
                    "assignments": [{"name": "x", "value": expression}],
                },
            },
        ],
        "connections": [{"source_node": "t", "target_node": "s"}],
    }
    create = await client.post(
        "/api/v1/workflows", json=body, headers=auth_headers,
    )
    # Creation is allowed — expressions are validated at *execution* time.
    assert create.status_code in (200, 201), create.text
    workflow_id = create.json()["id"]

    run = await client.post(
        f"/api/v1/workflows/{workflow_id}/execute", headers=auth_headers,
    )
    # The engine must either refuse the expression or surface an error
    # item — never a 500 and never a successful shell-out.
    assert run.status_code < 500, run.text
    if run.status_code == 200:
        payload = run.json()
        assert payload.get("status") in {"error", "failed", "success"}
        # If it "succeeded", the value must be the raw template string or
        # an explicit error marker — never the output of the injected call.
        if payload.get("status") == "success":
            dumped = str(payload)
            assert "uid=" not in dumped  # `id` output
            assert "root:" not in dumped  # /etc/passwd
