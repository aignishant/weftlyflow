"""Reserved for the richer lifespan logic added in Phase 2.

Current lifespan lives inline in :mod:`weftlyflow.server.app` for simplicity. When
the startup path grows beyond "configure logging" (leader election, scheduler
boot, migration-check, warm caches), move it here.
"""

from __future__ import annotations
