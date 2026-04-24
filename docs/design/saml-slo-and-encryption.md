# Design note: SAML SLO and encrypted assertions

**Status:** deferred — post-1.0 enterprise hardening.
**Owner:** unassigned.
**Related code:** `src/weftlyflow/auth/sso/saml.py`.

## Why this is deferred

The 1.0 SAML adapter deliberately ships **without** two features that
`python3-saml` supports:

1. **Single Log-Out (SLO).** Weftlyflow sessions are stateless
   access-token JWTs with short TTLs and a revocable refresh-token tail.
   SLO's value is "kill the user's session on the SP immediately when
   the IdP says so" — but for a stateless JWT, there is no session to
   kill server-side. The meaningful action (revoking the refresh
   token) is an out-of-band API call and does not need SAML plumbing.
   Every IdP support ticket we've seen asking for SLO can be solved
   by lowering the access-token TTL plus a `POST /auth/revoke` API.
2. **Encrypted assertions.** The transport is already TLS. Encrypted
   assertions defend against a very specific threat model — the IdP
   does not trust the SP's TLS terminator or any intermediate proxy.
   For a self-hosted tool, that threat model is exotic. Adding
   mandatory `xmlsec`-backed decryption also makes the ACS endpoint
   slower on every login for the 99% of deployments that don't need
   it.

Neither is a *security* deferral — both features exist, both are
opt-in, both can be bolted on without breaking the current adapter's
API.

## What SLO would require

1. **Config.** Extend `SAMLConfig` with `idp_slo_url`, `idp_slo_binding`
   (defaulting to HTTP-Redirect), and `sp_sls_url` (the SP's
   SingleLogoutService URL, analogous to `sp_acs_url`).
2. **Metadata.** Emit `<SingleLogoutService>` in the SP metadata XML
   when `sp_sls_url` is set. `_build_settings_dict` already threads
   through the OneLogin settings dict — add an
   `sp.singleLogoutService` block.
3. **Routes.** Three new FastAPI endpoints in
   `src/weftlyflow/server/routers/auth_sso_saml.py`:
   - `POST /api/v1/auth/sso/saml/logout` — SP-initiated; builds a
     `<LogoutRequest>` via `OneLogin_Saml2_Auth.logout(...)` and
     redirects.
   - `GET|POST /api/v1/auth/sso/saml/sls` — receives both
     IdP-initiated `<LogoutRequest>` and responses to SP-initiated
     requests; OneLogin's `process_slo` does the validation.
   - On successful SLO, call `RefreshTokenRepository.revoke_all(user_id)`
     so the user's active refresh tokens are invalidated. The access
     token will self-expire.
4. **Replay protection.** Reuse `NonceStore` (already used for OIDC /
   SAML login). Every `<LogoutRequest>` has an `ID`; store it on
   send, consume it on receive.
5. **Tests.** A handful of sandbox-style tests at
   `tests/unit/auth/sso/test_saml_slo.py` covering the SP-init and
   IdP-init paths, plus the replay case.

**Scope estimate:** ~400 lines of code, one Alembic migration for
the nonce cleanup index (if `RedisNonceStore` is not used).

## What encrypted assertions would require

Much smaller, because the library already supports it:

1. **Config.** Extend `SAMLConfig` with `want_assertions_encrypted:
   bool = False` and `sp_decryption_key: str = ""`.
2. **Settings.** Flip `security.wantAssertionsEncrypted = True` and
   put the decryption key into `sp.privateKey` (or a dedicated
   `sp.privateKeyNew` if the operator wants key rollover).
3. **Documentation.** Call out the `xmlsec` dependency more loudly
   in `docs/guide/single-sign-on.md`. Encrypted assertions force
   every login through a PKCS#1 decrypt.

**Scope estimate:** ~50 lines of code, entirely in `saml.py` +
docs. Lower-priority than SLO.

## When to build this

Trigger conditions, in rough order of likelihood:

- A first enterprise deployment explicitly asks for SLO as a
  compliance checkbox (SOC 2 / ISO 27001 reviews commonly flag
  missing SLO).
- Weftlyflow grows a server-side session model (the JWT tail is
  replaced by opaque session IDs). SLO becomes meaningful then and
  should ship in the same release.
- An operator reports a broken SLO-only IdP they cannot reconfigure.

Until one of those fires, this note is the authoritative pointer for
anyone asking "why isn't SLO implemented?" — the answer is
*intentionally deferred, not forgotten*.
