# Single Sign-On (SSO)

Weftlyflow ships two SSO protocols so most enterprise IdPs work out of the
box:

| Protocol | IdPs                                                        | Optional extra      |
| -------- | ----------------------------------------------------------- | ------------------- |
| OIDC     | Google Workspace, Entra / Azure AD, Okta, Auth0, Keycloak   | *(none — always on)* |
| SAML 2.0 | ADFS, Shibboleth, PingFederate, legacy enterprise IdPs      | `weftlyflow[sso]`    |

Both flows return the same signed access + refresh token pair a password
login does. SSO-authenticated users can auto-provision a local user row and
personal project on first login, or the operator can require every user
to be pre-provisioned.

!!! info "Environment variables"
    Every setting below is also the uppercase env-var with the
    `WEFTLYFLOW_` prefix — e.g. `WEFTLYFLOW_SSO_OIDC_ENABLED=true`.

## OIDC

### Required settings

```bash
WEFTLYFLOW_SSO_OIDC_ENABLED=true
WEFTLYFLOW_SSO_OIDC_ISSUER_URL=https://accounts.google.com
WEFTLYFLOW_SSO_OIDC_CLIENT_ID=<your-client-id>
WEFTLYFLOW_SSO_OIDC_CLIENT_SECRET=<your-client-secret>
WEFTLYFLOW_SSO_OIDC_REDIRECT_URI=https://weftlyflow.example.com/api/v1/auth/sso/oidc/callback
```

The adapter appends `/.well-known/openid-configuration` to the issuer URL
and discovers the authorization, token, and JWKS endpoints at boot. A
misconfiguration (blank required setting) fails server startup rather
than the first login attempt.

### Endpoints

| Method | Path                                       | Purpose                                       |
| ------ | ------------------------------------------ | --------------------------------------------- |
| GET    | `/api/v1/auth/sso/oidc/login`              | Redirects the browser to the IdP              |
| GET    | `/api/v1/auth/sso/oidc/callback`           | Consumes `?code=…&state=…`, mints local tokens |

### Example — Google Workspace

1. Create an OAuth 2.0 client in
   [Google Cloud Console](https://console.cloud.google.com/apis/credentials).
   Authorised redirect URI:
   `https://weftlyflow.example.com/api/v1/auth/sso/oidc/callback`.
2. Set the issuer to `https://accounts.google.com`.
3. Leave `sso_oidc_scopes` at the default (`openid email profile`).

### Example — Azure AD / Entra

1. Register an application in the Entra admin centre.
2. Issuer is
   `https://login.microsoftonline.com/<tenant-id>/v2.0`.
3. Add the redirect URI under *Authentication → Web*.

## SAML 2.0

### Install the optional extra

```bash
pip install 'weftlyflow[sso]'
```

This pulls in `python3-saml`, which links against `xmlsec`. On Debian-
family systems the prerequisite is `libxml2-dev libxmlsec1-dev
libxmlsec1-openssl pkg-config`.

### Required settings

```bash
WEFTLYFLOW_SSO_SAML_ENABLED=true
WEFTLYFLOW_SSO_SAML_SP_ENTITY_ID=https://weftlyflow.example.com/api/v1/auth/sso/saml/metadata
WEFTLYFLOW_SSO_SAML_SP_ACS_URL=https://weftlyflow.example.com/api/v1/auth/sso/saml/acs
WEFTLYFLOW_SSO_SAML_IDP_METADATA_XML='<?xml version="1.0"?><md:EntityDescriptor …>'
```

### Optional signed AuthnRequests

Set both of these to make the SP sign outbound AuthnRequests:

```bash
WEFTLYFLOW_SSO_SAML_SP_X509_CERT='-----BEGIN CERTIFICATE-----…'
WEFTLYFLOW_SSO_SAML_SP_PRIVATE_KEY='-----BEGIN PRIVATE KEY-----…'
```

`sso_saml_want_assertions_signed` defaults to **true**; keep it that way
outside of local development. Unsigned assertions are trivially forgeable
on the wire.

### Endpoints

| Method | Path                                      | Purpose                                              |
| ------ | ----------------------------------------- | ---------------------------------------------------- |
| GET    | `/api/v1/auth/sso/saml/metadata`          | SP metadata XML for the IdP administrator to import  |
| GET    | `/api/v1/auth/sso/saml/login`             | 302 to the IdP's SSO endpoint via HTTP-Redirect binding |
| POST   | `/api/v1/auth/sso/saml/acs`               | Assertion Consumer Service (HTTP-POST binding)       |

## Auto-provisioning

`sso_oidc_auto_provision` (OIDC) and `sso_saml_auto_provision` (SAML)
default to **true**. On first login:

1. Weftlyflow looks up the e-mail in the local users table.
2. If absent, it provisions a new user row plus a personal project (the
   user becomes the owner and is granted the `member` global role).
3. Subsequent logins from the same e-mail reuse the existing row.

Disable auto-provision in environments where user access is gated by a
separate admin workflow — the callback then returns **403 Forbidden** for
unknown e-mails.

## Replay protection

Every accepted callback consumes a single-use nonce embedded in the
signed `state` / `RelayState` token. A captured callback URL therefore
cannot be replayed within the 10-minute TTL window.

| Backend   | When to use                                                |
| --------- | ---------------------------------------------------------- |
| `memory`  | Default. Single API instance, no horizontal scaling.       |
| `redis`   | Two or more API replicas behind a load balancer.           |

```bash
WEFTLYFLOW_SSO_NONCE_STORE_BACKEND=redis
# Optional — defaults to the shared WEFTLYFLOW_REDIS_URL.
WEFTLYFLOW_SSO_NONCE_STORE_REDIS_URL=redis://sso-redis:6379/3
```

The Redis backend uses `SET NX EX` so the first-writer-wins decision is
atomic on the Redis server — no read-then-write race window.

## Post-login redirect

`sso_post_login_redirect` (default `/`) controls where the browser lands
after a successful login. The access + refresh tokens are attached as URL
**fragment** parameters (`#access_token=…&refresh_token=…`) so they
never hit the server access log or reverse-proxy logs.

The frontend is expected to read the fragment on page load, stash the
tokens, and strip the fragment from `window.location` before any router
navigation.

## Known limitations

- **SAML SLO (single log-out)** and **encrypted assertions** are both
  supported by `python3-saml` but intentionally not exposed. Weftlyflow
  sessions are stateless JWTs, so IdP-initiated logout would need a
  revocation list — out of scope for this tranche.
- **Scoped memory-backend in multi-instance deployments** is a
  footgun. If you run more than one API pod and leave
  `sso_nonce_store_backend=memory`, a callback may land on a different
  worker than the login and the nonce check becomes a no-op. Switch to
  the `redis` backend before scaling horizontally.
