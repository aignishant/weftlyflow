"""GitHub integration — issues, comments, repository metadata.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.github.node import GitHubNode

NODE = GitHubNode

__all__ = ["NODE", "GitHubNode"]
