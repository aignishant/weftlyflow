# Credentials

*Stub — populated in Phase 4.*

Encrypted auth secrets. Types: Bearer, Basic, API-key-in-header, API-key-in-query, generic OAuth2, per-service OAuth2. Fernet-encrypted at rest; key from `WEFTLYFLOW_ENCRYPTION_KEY`. Rotation via `MultiFernet`.

See `weftlyinfo.md §11`.
