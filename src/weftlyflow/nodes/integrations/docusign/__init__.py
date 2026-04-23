"""DocuSign eSignature integration — envelopes and templates.

Uses :class:`~weftlyflow.credentials.types.docusign_jwt.DocuSignJwtCredential`.
The node calls :func:`fetch_access_token` once per execution to obtain a
Bearer, then reuses it across the dispatch loop — DocuSign access
tokens are valid for ~1 hour, far longer than a single node run.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.docusign.node import DocuSignNode

NODE = DocuSignNode

__all__ = ["NODE", "DocuSignNode"]
