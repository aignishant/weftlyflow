"""Bitbucket Cloud integration — repositories, pull requests, issues.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.bitbucket.node import BitbucketNode

NODE = BitbucketNode

__all__ = ["NODE", "BitbucketNode"]
