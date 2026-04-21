"""Credential system — plugin types + Fernet encryption at rest.

Credential types are plugins (subclasses of :class:`BaseCredentialType` in
:mod:`weftlyflow.credentials.base`) that describe a shape (fields) and how to
apply the credential to an outgoing HTTP request.

Plaintext is never stored: :mod:`weftlyflow.credentials.cipher` encrypts with a
Fernet key loaded from :envvar:`WEFTLYFLOW_ENCRYPTION_KEY`. Key rotation uses
``MultiFernet``.

See IMPLEMENTATION_BIBLE.md §11.
"""

from __future__ import annotations
