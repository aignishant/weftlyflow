"""Observability utilities — logging, metrics, tracing.

See weftlyinfo.md §19.

The ``configure_logging`` helper lives in :mod:`weftlyflow.config.logging` (not
here) because it is a boot-time setup rather than a reusable runtime utility.
This package will grow in Phase 2 with Prometheus counter/histogram registries
and in Phase 8 with the OpenTelemetry bootstrap.
"""

from __future__ import annotations
