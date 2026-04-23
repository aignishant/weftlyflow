"""SAML 2.0 Web-Browser SSO adapter (SP-initiated, HTTP-Redirect + HTTP-POST).

Implements :class:`SSOProvider` on top of the ``python3-saml`` toolkit. Shipped
behind the ``sso`` optional-dependency group — importing this module without
``python3-saml`` installed raises ``ImportError`` at module load time.

What this adapter does:

1. Holds a parsed IdP descriptor (SSO endpoint, entity ID, signing cert)
   loaded once at startup from inline XML or a metadata URL.
2. Builds the ``AuthnRequest`` redirect URL (HTTP-Redirect binding), carrying
   the caller-supplied state token as the SAML ``RelayState`` parameter.
3. On the ACS callback (HTTP-POST binding): validates the ``SAMLResponse``
   signature, conditions, audience, and issuer; extracts ``NameID`` and the
   usual attribute claims; returns a :class:`SSOUserInfo`.
4. Emits the SP metadata XML on demand so the operator can hand it to the IdP
   administrator without round-tripping through a web UI.

What this adapter does **not** do:

* SLO (Single Log-Out). Weftlyflow sessions are stateless JWTs — IdP-initiated
  logout is a future feature tracked in IMPLEMENTATION_BIBLE.md §8b.
* Encrypted assertions. The library supports them but very few IdPs require
  encryption on top of TLS; we keep the default off to avoid the PKCS
  round-trip.
* Signature-bearing SP metadata. The emitted descriptor is unsigned; IdPs
  typically fingerprint-verify SP metadata out-of-band.

Design notes:

* **Sync library, async surface.** ``python3-saml`` is synchronous and does
  XML signature validation with ``xmlsec`` C bindings. We wrap the handful
  of blocking calls in :func:`asyncio.to_thread` so the provider conforms
  to :class:`SSOProvider` without adding Celery indirection.
* **No per-request client.** Unlike OIDC we never reach the IdP after the
  one-shot metadata load; the adapter is pure compute from then on.
* **NameID is the stable subject.** We prefer ``NameID`` over the e-mail
  attribute because some IdPs (Okta, Entra) rotate ``mail`` when a user's
  primary address changes.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any

from onelogin.saml2.auth import OneLogin_Saml2_Auth
from onelogin.saml2.idp_metadata_parser import OneLogin_Saml2_IdPMetadataParser
from onelogin.saml2.settings import OneLogin_Saml2_Settings

from weftlyflow.auth.sso.base import SSOError, SSOUserInfo

_POST_BINDING: str = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
_REDIRECT_BINDING: str = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
_NAMEID_EMAIL: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
_NAMEID_UNSPECIFIED: str = "urn:oasis:names:tc:SAML:1.1:nameid-format:unspecified"

# RFC 5322 lite. We deliberately exclude quoted-local-part and domain-literal
# forms — they are vanishingly rare in IdP NameIDs and widening the grammar
# makes the CR/LF-rejection guarantee harder to reason about.
_EMAIL_RE: re.Pattern[str] = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?"
    r"(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$",
)

# RFC 5321 §4.5.3.1.3 — upper bound on a forward path (<local@domain>) is
# 254 octets once the angle brackets are stripped. Anything beyond that is
# non-conforming and a red flag.
_MAX_EMAIL_LENGTH: int = 254


def _looks_like_email(candidate: str) -> bool:
    r"""Return True only for strings that are a safe ``local@domain.tld`` email.

    Specifically rejects:

    * Embedded CR/LF or other control characters (header-injection vector).
    * Multi-address payloads (``alice@a.com,bob@b.com``, ``\n``-separated).
    * Addresses without a TLD label.
    """
    if not candidate or len(candidate) > _MAX_EMAIL_LENGTH:
        return False
    if any(ch in candidate for ch in "\r\n\t\x00 "):
        return False
    return _EMAIL_RE.match(candidate) is not None


_EMAIL_ATTR_KEYS: tuple[str, ...] = (
    "email",
    "emailAddress",
    "mail",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
)
_NAME_ATTR_KEYS: tuple[str, ...] = (
    "displayName",
    "name",
    "cn",
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
)


@dataclass(slots=True, frozen=True)
class SAMLConfig:
    """Static configuration for a single SAML IdP ↔ SP pair.

    Attributes:
        sp_entity_id: SP's entity ID. Usually ``https://<host>/api/v1/auth/sso/saml/metadata``.
        sp_acs_url: The fully-qualified HTTPS URL where the IdP posts the
            ``SAMLResponse``. Must exactly match the IdP's registration.
        idp_metadata_xml: Full IdP metadata XML document. Either this or a
            URL-loaded metadata (see :meth:`SAMLProvider.from_metadata_url`)
            must populate the IdP descriptor before :meth:`prime` runs.
        x509_cert: Optional PEM-encoded SP signing cert. When both ``x509_cert``
            and ``private_key`` are set, AuthnRequests are signed.
        private_key: Optional PEM-encoded SP signing key.
        want_assertions_signed: Require the IdP's assertion XML be signed.
            Defaults to ``True`` and only turned off for local development.
    """

    sp_entity_id: str
    sp_acs_url: str
    idp_metadata_xml: str
    x509_cert: str = ""
    private_key: str = ""
    want_assertions_signed: bool = True


class SAMLProvider:
    """Adapter implementing :class:`SSOProvider` for SAML 2.0 IdPs.

    Example:
        >>> provider = SAMLProvider(config)  # doctest: +SKIP
        >>> await provider.prime()  # doctest: +SKIP
        >>> url = provider.authorization_url(state="<signed-state>")  # doctest: +SKIP
    """

    name: str = "saml"

    __slots__ = ("_config", "_idp", "_settings_dict")

    def __init__(self, config: SAMLConfig) -> None:
        """Bind the adapter to ``config`` but defer metadata parsing to :meth:`prime`."""
        self._config = config
        self._idp: dict[str, Any] | None = None
        self._settings_dict: dict[str, Any] | None = None

    async def prime(self) -> None:
        """Parse the IdP metadata XML and materialise the OneLogin settings dict.

        Safe to call repeatedly; subsequent calls are no-ops.
        """
        if self._settings_dict is not None:
            return
        idp = await asyncio.to_thread(
            OneLogin_Saml2_IdPMetadataParser.parse,
            self._config.idp_metadata_xml,
        )
        idp_section = idp.get("idp")
        if not idp_section:
            msg = "SAML IdP metadata does not contain an <IDPSSODescriptor>"
            raise SSOError(msg)
        self._idp = idp_section
        self._settings_dict = self._build_settings_dict(idp_section)
        # Validate eagerly — the toolkit raises a descriptive error for any
        # missing/invalid field and we want that surfaced at startup, not on
        # the first login attempt.
        OneLogin_Saml2_Settings(settings=self._settings_dict, sp_validation_only=False)

    def authorization_url(self, *, state: str) -> str:
        """Return the SSO redirect URL with ``state`` carried as ``RelayState``."""
        auth = self._make_auth(get_data={}, post_data={})
        # ``return_to`` is the OneLogin argument name for RelayState on login.
        target = auth.login(return_to=state)
        if not isinstance(target, str):
            msg = "OneLogin_Saml2_Auth.login() did not return a URL string"
            raise SSOError(msg)
        return target

    async def complete(self, params: dict[str, str]) -> SSOUserInfo:
        """Validate the posted ``SAMLResponse`` and return a :class:`SSOUserInfo`.

        Args:
            params: Flat dict representing the POST body — at minimum a
                ``SAMLResponse`` field; ``RelayState`` is handled by the
                caller before invoking this method.

        Raises:
            SSOError: The response failed signature, issuer, audience, or
                condition checks, or the assertion lacked a usable subject.
        """
        if "SAMLResponse" not in params:
            msg = "SAML callback missing SAMLResponse form field"
            raise SSOError(msg)
        auth = self._make_auth(get_data={}, post_data=params)
        await asyncio.to_thread(auth.process_response)
        errors = auth.get_errors()
        if errors:
            reason = auth.get_last_error_reason() or "unknown"
            msg = f"SAML response rejected: {', '.join(errors)} ({reason})"
            raise SSOError(msg)
        if not auth.is_authenticated():
            msg = "SAML response did not authenticate the subject"
            raise SSOError(msg)

        attributes = auth.get_attributes() or {}
        nameid = auth.get_nameid() or ""
        email = _pick_email(attributes, nameid, auth.get_nameid_format() or "")
        if not email:
            msg = "SAML assertion lacks an email attribute and NameID is not an email"
            raise SSOError(msg)
        issuer = self._require_idp().get("entityId", "")
        return SSOUserInfo(
            subject=nameid or email,
            email=email.lower(),
            # SAML has no standard "email verified" bit. Enterprise IdPs ship
            # only verified addresses; we treat any asserted email as verified.
            email_verified=True,
            issuer=str(issuer),
            display_name=_pick_name(attributes),
        )

    def metadata_xml(self) -> str:
        """Return the SP metadata XML so the operator can hand it to the IdP."""
        settings = OneLogin_Saml2_Settings(
            settings=self._raw_settings_dict(),
            sp_validation_only=True,
        )
        xml = settings.get_sp_metadata()
        errors = settings.validate_metadata(xml)
        if errors:
            msg = f"SP metadata failed self-validation: {', '.join(errors)}"
            raise SSOError(msg)
        if isinstance(xml, bytes):
            return xml.decode("utf-8")
        return str(xml)

    def _make_auth(
        self,
        *,
        get_data: dict[str, str],
        post_data: dict[str, str],
    ) -> OneLogin_Saml2_Auth:
        if self._settings_dict is None:
            msg = "SAMLProvider: call prime() before login/complete"
            raise SSOError(msg)
        # OneLogin expects a Flask-ish request dict. We always stamp HTTPS on
        # because Weftlyflow refuses to serve SAML over plain HTTP; the ACS URL
        # in config is the source of truth.
        request_data = {
            "https": "on",
            "http_host": _host_of(self._config.sp_acs_url),
            "server_port": "443",
            "script_name": _path_of(self._config.sp_acs_url),
            "get_data": get_data,
            "post_data": post_data,
        }
        return OneLogin_Saml2_Auth(request_data, old_settings=self._settings_dict)

    def _build_settings_dict(self, idp: dict[str, Any]) -> dict[str, Any]:
        signed = bool(self._config.x509_cert and self._config.private_key)
        return {
            "strict": True,
            "debug": False,
            "sp": {
                "entityId": self._config.sp_entity_id,
                "assertionConsumerService": {
                    "url": self._config.sp_acs_url,
                    "binding": _POST_BINDING,
                },
                "NameIDFormat": _NAMEID_EMAIL,
                "x509cert": self._config.x509_cert,
                "privateKey": self._config.private_key,
            },
            "idp": idp,
            "security": {
                "authnRequestsSigned": signed,
                "wantAssertionsSigned": self._config.want_assertions_signed,
                "wantMessagesSigned": False,
                "signMetadata": False,
                "requestedAuthnContext": False,
            },
        }

    def _raw_settings_dict(self) -> dict[str, Any]:
        """Return a settings dict valid for SP-metadata emission.

        Unlike :meth:`_build_settings_dict`, this works *before* :meth:`prime`
        has been called — the IdP section is absent and sp_validation_only
        is used to permit that.
        """
        if self._settings_dict is not None:
            return self._settings_dict
        placeholder_idp = {
            "entityId": "urn:weftlyflow:saml:idp-unprimed",
            "singleSignOnService": {
                "url": "https://idp.invalid/sso",
                "binding": _REDIRECT_BINDING,
            },
            "x509cert": "",
        }
        return self._build_settings_dict(placeholder_idp)

    def _require_idp(self) -> dict[str, Any]:
        if self._idp is None:
            msg = "SAMLProvider: IdP metadata not loaded — call prime()"
            raise SSOError(msg)
        return self._idp


def _pick_email(attributes: dict[str, Any], nameid: str, nameid_format: str) -> str:
    r"""Return a safe email for :class:`SSOUserInfo`, or ``""`` if none is trustworthy.

    Every candidate — whether it came from an attribute or from the NameID —
    must satisfy :func:`_looks_like_email`. A hostile IdP stuffing control
    characters into an ``unspecified`` NameID (``victim@corp\nattacker@evil``)
    is therefore rejected before it can become the local user row's email.
    """
    for key in _EMAIL_ATTR_KEYS:
        value = attributes.get(key)
        if value:
            candidate = str(value[0] if isinstance(value, list) else value)
            if _looks_like_email(candidate):
                return candidate
    if nameid and nameid_format in (_NAMEID_EMAIL, _NAMEID_UNSPECIFIED) and _looks_like_email(
        nameid,
    ):
        return nameid
    return ""


def _pick_name(attributes: dict[str, Any]) -> str | None:
    for key in _NAME_ATTR_KEYS:
        value = attributes.get(key)
        if value:
            return str(value[0] if isinstance(value, list) else value)
    return None


def _host_of(url: str) -> str:
    """Extract the host[:port] portion of an absolute HTTPS URL."""
    from urllib.parse import urlsplit  # noqa: PLC0415 — stdlib, leaf-only use

    parts = urlsplit(url)
    if parts.port is not None:
        return f"{parts.hostname}:{parts.port}"
    return parts.hostname or ""


def _path_of(url: str) -> str:
    from urllib.parse import urlsplit  # noqa: PLC0415

    return urlsplit(url).path or "/"
