"""GitLab integration — v4 REST API for issues and merge requests.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.gitlab.node import GitLabNode

NODE = GitLabNode

__all__ = ["NODE", "GitLabNode"]
