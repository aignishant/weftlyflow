# IP compliance (clean-room rules)

Weftlyflow is an **independent, original Python implementation**. To stay clean:

1. Read any upstream reference source only for architectural understanding, then close the file and write Weftlyflow code from scratch.
2. Never copy code, identifiers, display names, credential slugs, commit messages, test fixtures, or SVG icons.
3. Re-read the provider's official API documentation (not any third-party integration's page) when authoring an integration node. Cite it in the module docstring.
4. If a PR's provenance is uncertain, the author must state it in the PR description.
5. Automated check: the `ip-checker` agent scans staged diffs for red flags; a pre-write hook blocks obviously forbidden content from being written.

See `weftlyinfo.md §23` for the authoritative rules.
