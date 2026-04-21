"""FastAPI routers — one module per resource.

Conventions:
    * Routers live under ``/api/v1/<resource>`` except webhooks (``/webhook/*``).
    * Each router exposes a module-level ``router = APIRouter(...)``.
    * Business logic lives in services, never inline in the handler.
    * Request/response bodies use Pydantic DTOs from :mod:`weftlyflow.server.schemas`.
"""

from __future__ import annotations
