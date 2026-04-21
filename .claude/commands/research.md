---
description: Parallel deep research across docs, codebase, and prior art.
---

# /research

Answer a hard "how do we do X" question with multiple parallel Explore agents:

1. **Codebase agent** — search Weftlyflow + the n8n reference tree for existing patterns.
2. **Upstream docs agent** — check `context7` MCP for live docs of the relevant library (FastAPI, SQLAlchemy, Vue Flow, Celery, RestrictedPython, LangChain, ...).
3. **Web agent** (if enabled) — search for blog posts, RFCs, recent changelogs.

Synthesize into a single recommendation. Include:
- What we should do.
- Alternatives with tradeoffs.
- Sources cited.
- A follow-up question we need the user to answer before implementing.

Target 600–1000 words.
