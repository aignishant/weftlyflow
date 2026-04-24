"""Tier-1 utility nodes — the MVP core.

Each subpackage declares exactly one node and exports it as ``NODE`` so the
discovery walker in :mod:`weftlyflow.nodes.discovery` registers it on
``NodeRegistry.load_builtins()``.

Phase-1 line-up:
    manual_trigger : user-initiated workflow start.
    no_op          : pass-through (items unchanged).
    set_node       : add / remove / project JSON fields on items.
    if_node        : route items by a boolean predicate.
    code           : Python snippet runner (identity stub; sandbox in Phase 4).

Later phases will add switch_node, merge, filter, aggregate, wait, webhook,
schedule, split_in_batches, and http_request.

See weftlyinfo.md §25 (Tier 1).
"""

from __future__ import annotations
