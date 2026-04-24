"""Security test suite — authn/authz, webhook, expression, credentials.

Tests live under the ``security`` pytest marker and reuse the integration
fixtures (in-memory SQLite + bootstrapped admin). Every test asserts a
defensive behaviour — bad input rejected, tampered token refused,
privilege boundary held — rather than exercising a happy path.

Structure:
    test_auth_hardening.py     authentication boundary probes
    test_webhook_hardening.py  webhook ingress probes
    test_expression_injection.py  expression sandbox at the API boundary

Credential redaction is covered by
``tests/integration/test_credentials.py::test_credential_crud_no_plaintext_in_response``
(the integration suite already exercises the full create/list/test/delete
cycle and asserts plaintext never round-trips). Keep it there rather
than duplicating here — the security suite should reference it.

Adding a test:
    Import fixtures from ``tests.integration.conftest`` (they are pulled
    in via the root ``conftest.py`` autodiscovery). Mark the test with
    ``pytestmark = pytest.mark.security``. Prefer black-box probes — POST
    JSON at the public API rather than calling internal helpers.
"""
