"""Pipedrive integration — CRM v1 REST API for deals, persons, and more.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.pipedrive.node import PipedriveNode

NODE = PipedriveNode

__all__ = ["NODE", "PipedriveNode"]
