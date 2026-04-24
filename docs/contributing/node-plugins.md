# Writing a node plugin

A node is a Python class that subclasses `BaseNode` (action), `BaseTriggerNode` (event trigger), or `BasePollerNode` (interval poller). It declares a `NodeSpec` with its metadata and properties, and implements `execute()` / `setup()+teardown()` / `poll()`.

**Shortcut:** run the `/scaffold-node <slug> <display-name> <tier>` skill — it uses the `node-author` agent to generate a complete package, then the `ip-checker` agent verifies nothing looks copied.

**Adding a tier-3 (community) integration?** See [Tier-3
integrations](tier-3-integrations.md) — it covers the claim-a-slot
protocol, the in-tree vs third-party publishing paths, and the
review checklist specific to tier-3.

## Manual steps

1. Create `src/weftlyflow/nodes/<tier>/<slug>/` with `node.py`, `spec.py`, `__init__.py`, `icons/` and `README.md`.
2. Implement `execute()` / `trigger` methods.
3. Add tests at `tests/nodes/<slug>/` — at minimum: happy path, error path, `continue_on_fail`, property validation.
4. Cite the provider's **official** API docs in the module docstring. Never cite third-party integration pages.

## Non-negotiables (IP compliance)

- Do not copy code, identifiers, display names, or property descriptions from any upstream reference source.
- SVG icons sourced from Lucide / Simple Icons / hand-drawn.
- Test fixtures handcrafted or from the provider's docs.

See `IMPLEMENTATION_BIBLE.md §9` and `§23`.
