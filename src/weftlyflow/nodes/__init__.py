"""Node plugin system — built-in and community integration nodes.

Every node is a Python class that subclasses one of the abstract base classes
in :mod:`weftlyflow.nodes.base` and declares a :class:`NodeSpec` as a class
attribute. The :class:`NodeRegistry` discovers nodes via (a) package scan of
this subtree, (b) setuptools entry points under ``weftlyflow.nodes``, and (c)
an optional filesystem directory configured via ``WEFTLYFLOW_COMMUNITY_NODES_DIR``.

Packages:
    core         : Tier-1 utility nodes (HTTP, If, Set, Webhook, Schedule, Code, ...).
    integrations : Tier-2/3 service integrations (Slack, GitHub, Stripe, ...).
    ai           : LLM, agent, memory, vector-store, embedding nodes.

See IMPLEMENTATION_BIBLE.md §9 and §25.
"""

from __future__ import annotations
