"""Cloudinary integration — uploads, destroys, and resource admin.

Uses :class:`~weftlyflow.credentials.types.cloudinary_api.CloudinaryApiCredential`.
Upload and destroy requests are signed with
:func:`~weftlyflow.credentials.types.cloudinary_api.sign_params` (SHA-1
of ``sorted(params) + api_secret``); admin listings rely on the Basic
auth header that the credential injects.

Exposes the top-level ``NODE`` attribute consumed by built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.cloudinary.node import CloudinaryNode

NODE = CloudinaryNode

__all__ = ["NODE", "CloudinaryNode"]
