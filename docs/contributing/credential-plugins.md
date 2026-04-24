# Writing a credential plugin

A credential type is a subclass of `BaseCredentialType` in `src/weftlyflow/credentials/base.py`. It declares:

- `slug` — globally unique (`weftlyflow.stripe_api_key`).
- `display_name`.
- `properties` — form schema (reuses `PropertySchema`).
- `inject(creds, request)` — apply credential to an outgoing HTTP request.
- `test(creds)` — optional self-test.

Place the class under `src/weftlyflow/credentials/types/<slug>.py` (for generic types) or next to the integration node (for per-service credentials).

See `weftlyinfo.md §11`.
