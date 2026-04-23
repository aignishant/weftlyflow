"""Constants for the Mapbox integration node.

Reference: https://docs.mapbox.com/api/overview/.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_GEOCODING_ENDPOINT: Final[str] = "mapbox.places"
DEFAULT_DIRECTIONS_PROFILE: Final[str] = "mapbox/driving"

OP_FORWARD_GEOCODE: Final[str] = "forward_geocode"
OP_REVERSE_GEOCODE: Final[str] = "reverse_geocode"
OP_DIRECTIONS: Final[str] = "directions"
OP_MATRIX: Final[str] = "matrix"
OP_ISOCHRONE: Final[str] = "isochrone"

SUPPORTED_OPERATIONS: Final[tuple[str, ...]] = (
    OP_FORWARD_GEOCODE,
    OP_REVERSE_GEOCODE,
    OP_DIRECTIONS,
    OP_MATRIX,
    OP_ISOCHRONE,
)
