"""Pydantic DTOs for the HTTP surface.

One module per resource. These types are the **wire format** and are
translated to/from the domain dataclasses in :mod:`weftlyflow.domain` via
explicit mappers in each router. ORM entities never leak through this layer.
"""

from __future__ import annotations
