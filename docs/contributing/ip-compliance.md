# IP compliance (clean-room rules)

Weftlyflow is an **independent, original Python implementation inspired by n8n's architecture**. To stay clean:

1. Read the n8n source at `/home/nishantgupta/Downloads/n8n-master/` for architectural understanding, then close the file and write Weftlyflow code from scratch.
2. Never copy code, identifiers, display names, credential slugs, commit messages, test fixtures, or SVG icons.
3. Re-read the provider's official API documentation (not n8n's integration page) when authoring an integration node. Cite it in the module docstring.
4. If a PR's provenance is uncertain, the author must state it in the PR description.
5. Automated check: the `ip-checker` agent scans staged diffs for red flags; the `block-n8n-copy.sh` hook prevents obviously forbidden content from being written.

See `IMPLEMENTATION_BIBLE.md §23` for the authoritative rules.
