"""Supabase integration — PostgREST v1 surface for Supabase-hosted Postgres.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.supabase.node import SupabaseNode

NODE = SupabaseNode

__all__ = ["NODE", "SupabaseNode"]
