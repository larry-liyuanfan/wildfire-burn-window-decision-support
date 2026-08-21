"""Small, auditable helpers for applying polygon scopes to rectilinear grids."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


def _rings(geometry: dict[str, Any]) -> list[list[list[list[float]]]]:
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if geometry_type == "Polygon" and isinstance(coordinates, list):
        return [coordinates]
    if geometry_type == "MultiPolygon" and isinstance(coordinates, list):
        return coordinates
    raise ValueError("region geometry must be a GeoJSON Polygon or MultiPolygon")


def _points_in_ring(x: np.ndarray, y: np.ndarray, ring: list[list[float]]) -> np.ndarray:
    """Return a vectorised even-odd point-in-ring test.

    The official district boundary is simplified below the VicClim6 grid
    spacing before this function is called, so a dependency-heavy GIS stack is
    unnecessary for the 148 x 244 rectilinear grid.
    """

    coordinates = np.asarray(ring, dtype=float)
    if coordinates.ndim != 2 or coordinates.shape[0] < 4 or coordinates.shape[1] < 2:
        raise ValueError("GeoJSON ring must contain at least four coordinate pairs")
    inside = np.zeros(x.shape, dtype=bool)
    xj, yj = coordinates[-1, 0], coordinates[-1, 1]
    for xi, yi in coordinates[:, :2]:
        crosses = (yi > y) != (yj > y)
        denominator = yj - yi
        safe_denominator = denominator if denominator != 0 else np.finfo(float).eps
        boundary_x = (xj - xi) * (y - yi) / safe_denominator + xi
        inside ^= crosses & (x < boundary_x)
        xj, yj = xi, yi
    return inside


def geometry_mask(
    longitude: np.ndarray,
    latitude: np.ndarray,
    geometry: dict[str, Any],
) -> np.ndarray:
    """Rasterise GeoJSON polygon membership at rectilinear grid-cell centres."""

    lon_values = np.asarray(longitude, dtype=float)
    lat_values = np.asarray(latitude, dtype=float)
    if lon_values.ndim != 1 or lat_values.ndim != 1:
        raise ValueError("region masking requires one-dimensional latitude/longitude coordinates")
    x, y = np.meshgrid(lon_values, lat_values)
    result = np.zeros(x.shape, dtype=bool)
    for polygon in _rings(geometry):
        if not polygon:
            continue
        polygon_mask = _points_in_ring(x, y, polygon[0])
        for hole in polygon[1:]:
            polygon_mask &= ~_points_in_ring(x, y, hole)
        result |= polygon_mask
    return result


def subset_rectilinear_geojson(
    dataset: object,
    path: str | Path,
    *,
    latitude_name: str = "latitude",
    longitude_name: str = "longitude",
) -> tuple[object, dict[str, Any]]:
    """Select only grid centres inside a single-feature GeoJSON boundary."""

    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if payload.get("type") == "FeatureCollection":
        features = payload.get("features", [])
        if len(features) != 1:
            raise ValueError("region GeoJSON must contain exactly one feature")
        feature = features[0]
    elif payload.get("type") == "Feature":
        feature = payload
    else:
        feature = {"type": "Feature", "properties": {}, "geometry": payload}
    geometry = feature.get("geometry")
    if not isinstance(geometry, dict):
        raise TypeError("region GeoJSON feature has no geometry")
    if latitude_name not in dataset.coords or longitude_name not in dataset.coords:
        raise ValueError("dataset lacks the requested latitude/longitude coordinates")

    mask = geometry_mask(
        np.asarray(dataset[longitude_name].values),
        np.asarray(dataset[latitude_name].values),
        geometry,
    )
    selected = np.flatnonzero(mask.reshape(-1))
    if not selected.size:
        raise ValueError("region boundary selects no grid-cell centres")
    stacked = dataset.stack(
        spatial_cell=(latitude_name, longitude_name),
        create_index=False,
    ).isel(spatial_cell=selected)
    properties = feature.get("properties") or {}
    metadata = {
        "source_path": str(source.resolve()),
        "geometry_type": geometry.get("type"),
        "selected_grid_cells": int(selected.size),
        "total_grid_cells": int(mask.size),
        "coverage_fraction_of_source_grid": float(selected.size / mask.size),
        "feature_properties": {str(key): value for key, value in properties.items()},
        "boundary_provenance": payload.get("_provenance"),
        "coordinate_reference_system": "EPSG:4326 grid-cell centres",
        "boundary_inclusion_rule": "even-odd point-in-polygon at cell centre",
    }
    return stacked, metadata
