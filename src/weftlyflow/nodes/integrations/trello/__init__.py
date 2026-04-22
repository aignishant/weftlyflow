"""Trello integration — board and card CRUD via v1 REST API.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.trello.node import TrelloNode

NODE = TrelloNode

__all__ = ["NODE", "TrelloNode"]
