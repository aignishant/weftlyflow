# External secret providers

By default, a credential's payload is encrypted with the Fernet key and
stored in the `credentials` table. That's the right choice for small
deployments — one key to rotate, one database to back up — but larger
installations often need secrets to live in an existing vault rather than
Weftlyflow's database:

- **Rotation outside the app.** When an upstream token rotates in Vault,
  Weftlyflow must not require a re-encrypt of its DB.
- **Compliance.** Some regulatory regimes forbid secret material from
  living in application storage alongside business data.
- **Dev ergonomics.** Contributors should be able to point credentials at
  their shell environment without booting a Vault server.

Weftlyflow solves this with the **secret provider registry**: a credential
value may be a literal string *or* an opaque reference like
`vault:kv/data/slack#bot_token`. The provider registered for the `vault`
scheme is invoked at workflow-run time to dereference the value.

## Reference syntax

All backends share the same grammar:

```
<scheme>:<path>[#<field>]
```

- `scheme` picks the backend (`env`, `vault`, `op`, `aws`).
- `path` is whatever that backend uses to locate one secret (Vault path,
  1Password item UUID, AWS secret id, env var name).
- `#field` — optional — plucks a single key from a JSON payload. Without
  it, the raw secret string is returned.

## Built-in backends

### `env:` — environment variables (always on)

No configuration required. Use for dev, CI, or any deploy where the
operator already wires secrets into the process env.

```
env:SLACK_BOT_TOKEN
```

### `vault:` — HashiCorp Vault (KV v2)

| Setting                         | Required | Meaning                                    |
| ------------------------------- | :------: | ------------------------------------------ |
| `WEFTLYFLOW_VAULT_ENABLED`      |   yes    | Register the provider at boot              |
| `WEFTLYFLOW_VAULT_ADDRESS`      |   yes    | Vault base URL, e.g. `https://vault:8200`  |
| `WEFTLYFLOW_VAULT_TOKEN`        |   yes    | Token sent via `X-Vault-Token`             |
| `WEFTLYFLOW_VAULT_NAMESPACE`    |          | Vault Enterprise namespace                 |
| `WEFTLYFLOW_VAULT_TIMEOUT_SECONDS` |      | Per-request HTTP timeout (default 5.0)     |

Reference form targets a KV v2 mount:

```
vault:kv/data/slack#bot_token
vault:kv/data/deploys/prod#jwt_signing_key
```

Operational notes:

- Path includes the `/data/` segment — that's where KV v2 stores values,
  unlike KV v1.
- The token's policy must grant `read` on every path Weftlyflow will
  dereference. Prefer a per-deployment AppRole over the root token.
- Token renewal is out of scope for the provider; use Vault Agent or a
  sidecar if you need automatic renewal.

### `op:` — 1Password Connect

| Setting                                    | Required | Meaning                                    |
| ------------------------------------------ | :------: | ------------------------------------------ |
| `WEFTLYFLOW_ONEPASSWORD_ENABLED`           |   yes    | Register the provider at boot              |
| `WEFTLYFLOW_ONEPASSWORD_CONNECT_URL`       |   yes    | Connect base URL, e.g. `http://connect:8080` |
| `WEFTLYFLOW_ONEPASSWORD_CONNECT_TOKEN`     |   yes    | Connect bearer token                       |
| `WEFTLYFLOW_ONEPASSWORD_TIMEOUT_SECONDS`   |          | Per-request HTTP timeout (default 5.0)     |

Reference form points at an item and optionally a field label:

```
op:vaults/abcd1234.../items/wxyz5678...#password
```

Fetch vault and item UUIDs with the Connect `1password/v1/vaults` and
`1password/v1/items` endpoints, or with the `op` CLI.

### `aws:` — AWS Secrets Manager

Behind the `aws-secrets` optional extra:

```bash
pip install 'weftlyflow[aws-secrets]'
```

| Setting                          | Required | Meaning                                    |
| -------------------------------- | :------: | ------------------------------------------ |
| `WEFTLYFLOW_AWS_SECRETS_ENABLED` |   yes    | Register the provider at boot              |
| `WEFTLYFLOW_AWS_SECRETS_REGION`  |          | Region override (else boto3 default chain) |

Credentials come from the standard boto3 chain — static env vars on the
workstation, IRSA on EKS, task role on ECS, instance profile on EC2. Keep
static access keys out of the process env in production.

Reference form accepts both names and ARNs:

```
aws:prod/slack#bot_token
aws:arn:aws:secretsmanager:us-east-1:123456789012:secret:prod/slack-AbCdEf
```

When `#field` is set, the provider JSON-decodes the `SecretString` and
returns the named key; without it, the raw string is returned.

## Troubleshooting

| Symptom                                                       | Likely cause                                                                |
| ------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `UnknownSecretSchemeError: vault`                             | `WEFTLYFLOW_VAULT_ENABLED=true` but missing address/token — server fails fast at boot |
| `SecretNotFoundError: vault:kv/data/...`                      | Path wrong or token policy lacks `read` permission                          |
| `VaultAuthError: 403`                                         | Token valid but policy denies this path                                     |
| `AWSSecretsManagerAuthError: AccessDeniedException`           | IAM principal lacks `secretsmanager:GetSecretValue`                         |
| `ImportError: boto3`                                          | `aws_secrets_enabled=true` without the `aws-secrets` extra installed        |
| Dereferenced value is empty / `None` in the workflow          | JSON payload doesn't have the `#field` you asked for; check the secret      |

Look for `secret_provider` bound entries in the structured log to trace a
specific lookup — each dereference emits an event at `debug` level.

## Registering a custom provider

Implement the :class:`SecretProvider` protocol (async `get`, a `scheme`
class attribute) and register it during app startup. A minimal example:

```python
from weftlyflow.credentials.external import (
    SecretProvider, SecretReference, SecretProviderRegistry,
)

class GcpSecretProvider:
    scheme = "gcp"
    async def get(self, ref: SecretReference) -> str:
        ...  # call google-cloud-secret-manager here

# In your app factory override:
registry.register(GcpSecretProvider())
```

There is no auto-discovery — providers must be registered explicitly so
an operator sees exactly which backends the running process trusts.
