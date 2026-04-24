"""FastAPI application — HTTP + WebSocket surface for Weftlyflow.

The app is produced by :func:`weftlyflow.server.app.create_app`. A module-level
``app`` is exposed for convenience so uvicorn can find it with the string
``weftlyflow.server.app:app``.

Layers:
    schemas/  : Pydantic DTOs (request/response bodies).
    routers/  : One router per resource.
    deps.py   : FastAPI dependencies (DB, current user, project context).
    middleware.py : request-id, logging, error envelope, CORS.
    errors.py : map domain exceptions to HTTPException.
    lifespan.py : startup/shutdown (scheduler, leader election, migrations check).

See weftlyinfo.md §15 for the full endpoint list.
"""

from __future__ import annotations
