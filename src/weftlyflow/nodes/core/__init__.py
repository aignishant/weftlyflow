"""Tier-1 utility nodes — the MVP core.

Each subpackage contains exactly one node:
    http_request/   — issue arbitrary HTTP requests.
    webhook/        — receive HTTP events as triggers.
    schedule/       — cron / interval trigger.
    manual_trigger/ — user-initiated run.
    if_node/        — boolean branching.
    switch_node/    — multi-way routing.
    merge/          — combine parallel branches.
    set/            — set, rename, or remove properties on items.
    split_in_batches/ — chunk a list for per-chunk downstream processing.
    code/           — run sandboxed Python snippets.
    filter/         — keep items matching a predicate.
    aggregate/      — collapse a list of items into one.
    wait/           — pause execution (timer or external signal).
    no_op/          — pass-through.

See IMPLEMENTATION_BIBLE.md §25 (Tier 1).
"""

from __future__ import annotations
