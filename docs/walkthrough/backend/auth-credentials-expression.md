# Auth, Credentials, Expression

> The three security-sensitive subpackages. Read each section carefully before
> proposing changes — the failure modes here are subtle and the blast radius
> is large.

## `auth/` — identity and access

:material-folder: `src/weftlyflow/auth/`

### Files

| File | Purpose |
| ---- | ------- |
| `passwords.py` | Argon2id hash + verify wrappers. |
| `jwt.py` | JWT issue, decode, refresh-token rotation. |
| `scopes.py` | RBAC scope definitions and the `require_scope` helper. |
| `bootstrap.py` | First-boot admin + project seed. |
| `views.py` | Helpers shared by `auth` + `oauth2` routers. |
| `constants.py` | Token TTLs, JWT algorithms, scope strings. |
| `sso/` | OIDC + SAML providers + nonce store + state token. |
| `__init__.py` | Public surface. |

### `auth/passwords.py`

| Function | Purpose |
| -------- | ------- |
| `hash_password(plain) -> str` | Argon2id, parameters from settings. Returns the standard PHC-format string. |
| `verify_password(plain, encoded) -> bool` | Constant-time. Catches `argon2.exceptions.VerifyMismatchError` and returns False. |
| `needs_rehash(encoded) -> bool` | True if hashing parameters were upgraded since `encoded` was generated. Caller re-hashes on next successful login. |

### `auth/jwt.py`

Two token types:

| Token | TTL | Where stored |
| ----- | --- | ------------ |
| Access | `jwt_access_ttl_seconds` (default ~15 min) | Returned to client; not persisted server-side. |
| Refresh | `jwt_refresh_ttl_seconds` (default ~30 days) | Persisted in `refresh_tokens` table; revocable; rotated on use. |

| Function | Purpose |
| -------- | ------- |
| `issue_access_token(user, *, scopes)` | Sign with HS256 and `jwt_secret`. Carries `sub`, `scopes`, `exp`, `iat`. |
| `issue_refresh_token(user)` | Generate ulid + persist `RefreshTokenEntity`. |
| `decode_access_token(token) -> Claims` | Verifies signature + expiry. Raises `AuthenticationError`. |
| `rotate_refresh_token(token, session)` | Atomic: revoke old row, insert new one, return new pair. |

### `auth/scopes.py` — RBAC

Scopes are flat strings: `workflows:read`, `workflows:write`,
`executions:read`, `credentials:write`, `admin`. The `require_scope(name)`
factory in `server/deps.py` builds a `Depends(...)` that asserts the JWT
carries the named scope.

### `auth/bootstrap.py` — `ensure_bootstrap_admin`

On boot, if `users` is empty:

1. Read `WEFTLYFLOW_BOOTSTRAP_ADMIN_EMAIL` + `_PASSWORD` from env.
2. Insert a `UserEntity` with `admin` scope.
3. Create a default `ProjectEntity` and assign the user as owner.
4. Log a warning on stdout: "Bootstrap admin created — change the password."

### `auth/sso/` — federated identity

| File | Provides |
| ---- | -------- |
| `base.py` | `SSOProvider` Protocol + `SSOAttributes` dataclass. |
| `oidc.py` | `OIDCConfig`, `OIDCProvider`. Discovery (`/.well-known/openid-configuration`), authorization-code-with-PKCE, ID-token verification, JIT user provisioning. |
| `saml.py` | `SAMLConfig`, `SAMLProvider`. Wraps `python3-saml`. SP-init flow only; metadata at `/api/v1/sso/saml/metadata`. |
| `nonce_store.py` | `NonceStore` Protocol + `InMemoryNonceStore` + `RedisNonceStore`. Tracks consumed `nonce` claims so OIDC tokens cannot be replayed. |
| `state_token.py` | Signed CSRF state token used during the OIDC redirect dance. |

The provider integration is *opt-in*: `WEFTLYFLOW_SSO_OIDC_ENABLED` /
`WEFTLYFLOW_SSO_SAML_ENABLED`. Missing required settings raise at boot, not
at login time, so misconfiguration fails loudly.

---

## `credentials/` — secret management

:material-folder: `src/weftlyflow/credentials/`

### Files

| File | Purpose |
| ---- | ------- |
| `base.py` | `BaseCredentialType` ABC + `CredentialField` dataclass + helpers. |
| `cipher.py` | :material-shield-lock: `CredentialCipher` (Fernet, with old-key rotation). |
| `registry.py` | `CredentialTypeRegistry` keyed by `name`. |
| `resolver.py` | `CredentialResolver` Protocol + `DatabaseCredentialResolver`. |
| `external/` | External secret providers (Env, Vault, 1Password, AWS). |
| `types/` | One module per credential type (~80 of them). |

### `credentials/cipher.py` — `CredentialCipher` :material-shield-lock:

| Method | Purpose |
| ------ | ------- |
| `encrypt(payload: dict) -> bytes` | JSON-serialise → Fernet encrypt with current key. |
| `decrypt(blob: bytes) -> dict` | Try current key first, then each `old_keys` entry. Re-encrypts on next write to migrate forward. |

The constructor accepts a single current key + a list of `old_keys`. Key
rotation is a two-step deploy:

1. Add new key to `WEFTLYFLOW_ENCRYPTION_KEY`, move old to
   `WEFTLYFLOW_ENCRYPTION_KEY_OLD_KEYS` (comma-separated). Deploy.
2. After every credential has been touched (write or background re-encrypt),
   remove the old key from `OLD_KEYS`. Deploy.

`generate_key()` wraps `cryptography.fernet.Fernet.generate_key()`.

### `credentials/registry.py` — `CredentialTypeRegistry`

| Method | Purpose |
| ------ | ------- |
| `register(type_cls)` | Add a `BaseCredentialType` subclass keyed by `type_cls.name`. |
| `get(name)` | Resolve to the class. Raises `KeyError`. |
| `iter_types()` | Iterate for `/api/v1/credential-types`. |
| `load_builtins()` | Walk `credentials/types/` and register every subclass. |

### `credentials/resolver.py` — `DatabaseCredentialResolver`

```python
async def resolve(
    self,
    *,
    credential_id: str,
    project_id: str,
) -> dict[str, Any]:
    """Fetch row, decrypt, optionally substitute external-provider refs."""
```

Steps:

1. `CredentialRepository.get(...)` → `CredentialEntity`.
2. `cipher.decrypt(entity.encrypted_body)` → `dict`.
3. For any field with value matching `${provider:ref}`: call the external
   provider, substitute the resolved secret. Provider chain is queried in
   registration order; the first match wins.
4. Return the merged dict.

The decrypted body is **never logged**. The resolver is async so external
providers (Vault, 1Password) can do network IO without blocking.

### `credentials/external/` — pluggable secret providers

| File | Provider |
| ---- | -------- |
| `base.py` | `SecretProvider` Protocol — `name: str`, `async fetch(ref: str) -> str`. |
| `registry.py` | `SecretProviderRegistry` — ordered list of providers. |
| `env_provider.py` | `EnvSecretProvider` — `${env:VAR_NAME}` from `os.environ`. Always registered. |
| `vault_provider.py` | `VaultSecretProvider` — HashiCorp Vault KVv2. Requires `vault_address` + `vault_token`. |
| `onepassword_provider.py` | `OnePasswordSecretProvider` — 1Password Connect HTTP API. |
| `aws_provider.py` | `AWSSecretsManagerProvider` — boto3-based. Lazy import — `aws-secrets` extra. |

### `credentials/types/` — per-service credential schemas

One module per credential type. Each defines:

```python
class OpenAICredential(BaseCredentialType):
    name = "openai_api"
    display_name = "OpenAI API Key"
    fields = [
        CredentialField(name="api_key", label="API key", type="password", required=True),
        CredentialField(name="organization", label="Organization id", type="string"),
    ]
    test_endpoint = "https://api.openai.com/v1/models"
```

The registry uses `fields` to render the credential form in the UI, and
`test_endpoint` (when present) for the "Test credential" button.

---

## `expression/` — `{{ ... }}` template engine :material-shield-lock:

:material-folder: `src/weftlyflow/expression/`

### Files

| File | Purpose |
| ---- | ------- |
| `tokenizer.py` | Splits a string into `LiteralChunk` / `ExpressionChunk`. |
| `sandbox.py` | RestrictedPython compile + guarded eval. |
| `proxies.py` | The `$`-prefixed objects exposed in expressions. |
| `resolver.py` | Glues the above + an LRU cache for compiled expressions. |
| `errors.py` | `ExpressionError` family. |
| `__init__.py` | Re-exports public surface (`resolve`, `resolve_tree`, proxies). |

### `expression/tokenizer.py`

| Function | Purpose |
| -------- | ------- |
| `tokenize(template) -> list[Chunk]` | Split on `{{ ... }}` boundaries. |
| `contains_expression(template) -> bool` | Cheap predicate: does the string have any `{{`? |
| `is_single_expression(template) -> bool` | True when the template is *only* `{{ ... }}` (with optional whitespace) — lets the resolver return the native Python value rather than a string. |

`LiteralChunk(text)` and `ExpressionChunk(code)` are frozen dataclasses.

### `expression/sandbox.py` :material-shield-lock:

The hardened compile + eval boundary. Wraps RestrictedPython:

- **Compile** — `compile_restricted_eval(source, filename, mode='eval')`.
  Only expression mode (no statements). Disallows `import`, `exec`, `eval`,
  attribute access to `__class__`, `__bases__`, `func_globals`, etc.
- **Globals** — a curated dict containing only the allowed proxies + a small
  builtins subset (`len`, `min`, `max`, `int`, `float`, `str`, `bool`,
  `dict`, `list`, `tuple`, `range`, `sorted`, `reversed`, `enumerate`,
  `zip`, `abs`, `round`, `sum`, `any`, `all`, `repr`).
- **Locals** — empty (no leakage between expressions).
- **Timeout** — every eval runs with a thread-level deadline
  (`expression_timeout_ms`); exceeding raises `ExpressionTimeoutError`.
- **Caching** — compiled byte code is cached in an LRU keyed by source
  string. `clear_cache()` is exposed for tests.

### `expression/proxies.py` — what's in scope

| Symbol | Provides |
| ------ | -------- |
| `$json` | The current item's `.json` dict. |
| `$binary` | The current item's `.binary` map. |
| `$item` | The full current `Item` (json + binary + paired_item). |
| `$input` | `InputProxy` — `.all()`, `.first()`, `.last()`, `.itemMatching(idx)`. |
| `$node["Name"]` | Read from another node's last run output. |
| `$node["Name"].json[idx]` | Indexed access into another node's items. |
| `$now` | `WeftlyflowDateTime` — Luxon-style datetime helpers (`.minus({days:1})`, `.toISO()`, `.format("...")`). |
| `$today` | Today as `WeftlyflowDateTime` at 00:00 UTC. |
| `$workflow` | `{ id, name, active }` of the current workflow. |
| `$execution` | `{ id, mode, retry_of }` of the current run. |
| `$env` | Filtered `os.environ` — only keys in `exposed_env_var_list`. |
| `$secrets` | Decrypted secrets (lazy — only fetched when accessed). |
| `$vars` | Per-workflow `static_data`. |

The `build_proxies(ctx)` factory assembles the dict for a given
`ExecutionContext`. `filter_env(env, *, allowlist)` is the env-narrowing
helper.

### `expression/resolver.py`

| Function | Purpose |
| -------- | ------- |
| `resolve(template, ctx) -> Any` | Tokenize → eval each expression chunk → re-stitch. Returns the native Python value when `is_single_expression(template)`; otherwise returns a string. |
| `resolve_tree(value, ctx) -> Any` | Walk a nested dict / list / tuple, calling `resolve` on every string leaf that `contains_expression`. |
| `clear_cache()` | Drop the compiled-expression LRU. |

The executor calls `resolve_tree(node.parameters, ctx)` once per node before
invoking `node.execute(...)`, so node code receives parameter values that
have already been resolved.

### Failure modes (read before changing this code)

| Error | Raised when |
| ----- | ----------- |
| `ExpressionSyntaxError` | RestrictedPython compile error. |
| `ExpressionEvalError` | Runtime exception during eval. |
| `ExpressionSecurityError` | Disallowed operation (e.g. attribute access to `__class__`). |
| `ExpressionTimeoutError` | Exceeded `expression_timeout_ms`. |

All four derive from `ExpressionError`. The executor catches them, marks the
node failed, and routes the message through `safe_error_message` so a
malformed expression cannot leak environment values via the message.

## Cross-references

- The same RestrictedPython compiler runs untrusted Code-node scripts in a
  subprocess sandbox: [Triggers, Worker, Webhooks](triggers-worker-webhooks.md).
- The `ExecutionContext` that calls `resolve_tree(...)`:
  [Domain → Engine → Nodes](domain-engine-nodes.md).
- HTTP error mapping for `AuthenticationError` etc.:
  [Server & DB](server-db.md).
