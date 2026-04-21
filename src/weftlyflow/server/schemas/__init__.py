"""Pydantic DTOs for the HTTP surface.

One module per resource. These types are the **wire format** — they are
translated to/from the domain dataclasses in :mod:`weftlyflow.domain` via
explicit mappers kept next to each router. Never leak ORM entities here.
"""

from __future__ import annotations
