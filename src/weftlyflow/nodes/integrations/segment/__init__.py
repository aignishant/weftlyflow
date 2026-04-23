"""Segment integration — Track/Identify/Group/Page/Alias ingestion.

Authenticated via the shared
:class:`~weftlyflow.credentials.types.segment_write_key.SegmentWriteKeyCredential`
which sends the source write key as HTTP Basic *username* with an
empty password.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.segment.node import SegmentNode

NODE = SegmentNode

__all__ = ["NODE", "SegmentNode"]
