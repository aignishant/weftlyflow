"""Per-operation request builders for the Mapbox node.

Each builder returns ``(http_method, path, body, query)``. Paths are
relative to ``https://api.mapbox.com``.

Distinctive Mapbox shape: every Mapbox API takes the search term *in
the URL path* (percent-encoded) and takes scalar filters via the query
string. The ``access_token`` query param is added centrally by the
credential — builders must not emit it.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from weftlyflow.nodes.integrations.mapbox.constants import (
    DEFAULT_DIRECTIONS_PROFILE,
    DEFAULT_GEOCODING_ENDPOINT,
    OP_DIRECTIONS,
    OP_FORWARD_GEOCODE,
    OP_ISOCHRONE,
    OP_MATRIX,
    OP_REVERSE_GEOCODE,
)

RequestSpec = tuple[str, str, dict[str, Any] | None, dict[str, Any]]


def build_request(operation: str, params: dict[str, Any]) -> RequestSpec:
    """Dispatch ``operation`` to its builder or raise :class:`ValueError`."""
    builder = _BUILDERS.get(operation)
    if builder is None:
        msg = f"Mapbox: unsupported operation {operation!r}"
        raise ValueError(msg)
    return builder(params)


def _build_forward_geocode(params: dict[str, Any]) -> RequestSpec:
    search = _required(params, "search_text")
    endpoint = str(params.get("endpoint") or DEFAULT_GEOCODING_ENDPOINT).strip()
    query: dict[str, Any] = {}
    for key in ("limit", "language", "country", "proximity", "bbox", "types", "autocomplete"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    path = f"/geocoding/v5/{endpoint}/{quote(search, safe='')}.json"
    return "GET", path, None, query


def _build_reverse_geocode(params: dict[str, Any]) -> RequestSpec:
    longitude = _required(params, "longitude")
    latitude = _required(params, "latitude")
    endpoint = str(params.get("endpoint") or DEFAULT_GEOCODING_ENDPOINT).strip()
    query: dict[str, Any] = {}
    for key in ("language", "types", "limit"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    path = f"/geocoding/v5/{endpoint}/{longitude},{latitude}.json"
    return "GET", path, None, query


def _build_directions(params: dict[str, Any]) -> RequestSpec:
    profile = str(params.get("profile") or DEFAULT_DIRECTIONS_PROFILE).strip()
    coordinates = _required(params, "coordinates")
    query: dict[str, Any] = {}
    for key in (
        "alternatives",
        "geometries",
        "overview",
        "steps",
        "annotations",
        "language",
        "exclude",
    ):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    path = f"/directions/v5/{profile}/{coordinates}"
    return "GET", path, None, query


def _build_matrix(params: dict[str, Any]) -> RequestSpec:
    profile = str(params.get("profile") or DEFAULT_DIRECTIONS_PROFILE).strip()
    coordinates = _required(params, "coordinates")
    query: dict[str, Any] = {}
    for key in ("annotations", "sources", "destinations"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    path = f"/directions-matrix/v1/{profile}/{coordinates}"
    return "GET", path, None, query


def _build_isochrone(params: dict[str, Any]) -> RequestSpec:
    profile = str(params.get("profile") or DEFAULT_DIRECTIONS_PROFILE).strip()
    coordinates = _required(params, "coordinates")
    query: dict[str, Any] = {}
    contours_minutes = params.get("contours_minutes")
    contours_meters = params.get("contours_meters")
    if contours_minutes in (None, "") and contours_meters in (None, ""):
        msg = "Mapbox: one of 'contours_minutes' or 'contours_meters' is required"
        raise ValueError(msg)
    if contours_minutes not in (None, ""):
        query["contours_minutes"] = _stringify(contours_minutes)
    if contours_meters not in (None, ""):
        query["contours_meters"] = _stringify(contours_meters)
    for key in ("contours_colors", "polygons", "denoise", "generalize"):
        value = params.get(key)
        if value not in (None, ""):
            query[key] = _stringify(value)
    path = f"/isochrone/v1/{profile}/{coordinates}"
    return "GET", path, None, query


def _stringify(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _required(params: dict[str, Any], key: str) -> str:
    value = str(params.get(key) or "").strip()
    if not value:
        msg = f"Mapbox: {key!r} is required"
        raise ValueError(msg)
    return value


_Builder = Callable[[dict[str, Any]], RequestSpec]
_BUILDERS: dict[str, _Builder] = {
    OP_FORWARD_GEOCODE: _build_forward_geocode,
    OP_REVERSE_GEOCODE: _build_reverse_geocode,
    OP_DIRECTIONS: _build_directions,
    OP_MATRIX: _build_matrix,
    OP_ISOCHRONE: _build_isochrone,
}
