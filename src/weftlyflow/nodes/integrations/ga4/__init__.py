"""Google Analytics 4 Measurement Protocol integration.

Uses :class:`~weftlyflow.credentials.types.ga4_measurement.Ga4MeasurementCredential`.
The credential injects ``measurement_id`` and ``api_secret`` as query
parameters on every request; the node is responsible for routing
between the production (``/mp/collect``) and debug (``/debug/mp/collect``)
endpoints and assembling the event batch envelope.

Exposes the top-level ``NODE`` attribute consumed by the built-in node
discovery in :mod:`weftlyflow.nodes.discovery`.
"""

from __future__ import annotations

from weftlyflow.nodes.integrations.ga4.node import Ga4Node

NODE = Ga4Node

__all__ = ["NODE", "Ga4Node"]
