# Security testing

Weftlyflow's security test suite lives under `tests/security/` and is
marked with `@pytest.mark.security`. These tests are **boundary
probes** — they POST at the public API and assert that the server
refuses or redacts rather than crashes or leaks.

Run:

```bash
make test-security
```

## What belongs in `tests/security/`

| File | Scope |
|------|-------|
| `test_auth_hardening.py` | Login, JWT, bearer-scheme, refresh, MFA |
| `test_webhook_hardening.py` | Webhook ingress parsing, size limits |
| `test_expression_injection.py` | Expression sandbox at the API boundary |

Credential redaction lives in the integration suite
(`tests/integration/test_credentials.py::test_credential_crud_no_plaintext_in_response`).
Keep it there rather than duplicating here.

A test belongs here when the question is **"does this defensive
behaviour hold under adversarial input?"** — not "does this feature
work." Happy-path coverage lives in `tests/integration/`.

## What *doesn't* belong here

- Unit-level sandbox tests — they live in
  `tests/unit/expression/test_sandbox_bypass_corpus.py` and
  `test_sandbox_fuzz.py`.
- Credential cipher round-trip — `tests/unit/credentials/test_cipher.py`.
- The boundary suite should stay small and fast; push detailed
  coverage down to the unit layer and keep this tier as a public-API
  regression net.

## Writing a new probe

1. Decide which boundary: auth, webhook, expression, credential, or a
   new one.
2. Mark the module: `pytestmark = pytest.mark.security`.
3. Re-use `client`, `access_token`, `auth_headers` from
   `tests.security.conftest` — those forward the integration fixtures.
4. Assert `status_code < 500` at minimum. A 4xx with a neutral error
   body is almost always the correct answer.
5. When asserting "the secret does not leak," assert against `.text`
   rather than `.json()` — catches the case where the key moves inside
   a nested object.

## Third-party scans

Static and dependency scanning is intentionally *not* wired in this
repo yet. Recommended cadence for release cuts:

- **`pip-audit`** on the locked dev+runtime set.
- **`bandit -r src/weftlyflow`** — focus on the engine, sandbox, and
  webhook ingress; everything else is noise.
- **`trivy image ghcr.io/<org>/weftlyflow-api:<tag>`** after the
  release workflow builds the Docker images.

Add findings as new probes in this suite rather than fixing silently —
the test codifies the mitigation.
