"""Node plugin system — built-in and community integration nodes.

Every node is a Python class that subclasses one of the abstract base classes
in :mod:`weftlyflow.nodes.base` and declares a :class:`NodeSpec` as a class
attribute. The class is exposed as a top-level ``NODE`` attribute on its
module so the discovery walker in :mod:`weftlyflow.nodes.discovery` picks it
up without any decorator call at import time.

Packages:
    core         : Tier-1 utility nodes shipped with Weftlyflow.
    integrations : Tier-2/3 service integrations (Slack, GitHub, Stripe, ...).
    ai           : LLM, agent, memory, vector-store, embedding nodes.

Public surface:
    NodeRegistry      : lookup + versioning.
    register_node     : decorator that registers on a given registry.
    NodeRegistryError : raised for duplicate / malformed registrations.

See IMPLEMENTATION_BIBLE.md §9 and §25.
"""

from __future__ import annotations

from weftlyflow.nodes.registry import (
    NodeRegistry,
    NodeRegistryError,
    register_node,
)

__all__ = [
    "NodeRegistry",
    "NodeRegistryError",
    "register_node",
]
