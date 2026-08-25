"""Area-weighted contracts between official burn polygons and VicClim6 grids."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


def coordinate_edges(values: Sequence[float] | np.ndarray) -> np.ndarray:
    centres = np.asarray(values, dtype=float)
    if centres.ndim != 1 or len(centres) < 2:
        raise ValueError("grid coordinates must be one-dimensional with at least two centres")
    differences = np.diff(centres)
    if np.any(differences == 0) or not (np.all(differences > 0) or np.all(differences < 0)):
        raise ValueError("grid coordinates must be strictly monotonic")
    edges = np.empty(len(centres) + 1, dtype=float)
    edges[1:-1] = (centres[:-1] + centres[1:]) / 2.0
    edges[0] = centres[0] - differences[0] / 2.0
    edges[-1] = centres[-1] + differences[-1] / 2.0
    return edges


def build_area_weighted_overlay(
    feature_collection: Mapping[str, Any],
    *,
    latitude: Sequence[float] | np.ndarray,
    longitude: Sequence[float] | np.ndarray,
    id_property: str = "TREAT_NO",
) -> dict[str, Any]:
    """Intersect official EPSG:4326 polygons with each rectilinear grid cell.

    Cell and overlap areas are calculated after projection to Australian Albers
    (EPSG:3577). Zero-coverage burn units remain explicit in the output and are
    never replaced by a nearest grid cell.
    """

    from pyproj import Transformer
    from shapely.geometry import box, shape
    from shapely.ops import transform, unary_union
    from shapely.validation import make_valid

    if feature_collection.get("type") != "FeatureCollection":
        raise ValueError("burn geometry input must be a GeoJSON FeatureCollection")
    lat = np.asarray(latitude, dtype=float)
    lon = np.asarray(longitude, dtype=float)
    lat_edges = coordinate_edges(lat)
    lon_edges = coordinate_edges(lon)
    transformer = Transformer.from_crs(4326, 3577, always_xy=True)

    by_id: dict[str, list[Any]] = defaultdict(list)
    properties_by_id: dict[str, dict[str, Any]] = {}
    for feature in feature_collection.get("features", []):
        properties = feature.get("properties") or {}
        burn_id = str(properties.get(id_property, "")).strip()
        geometry = feature.get("geometry")
        if not burn_id or not geometry:
            continue
        parsed = shape(geometry)
        if not parsed.is_valid:
            parsed = make_valid(parsed)
        if parsed.is_empty:
            continue
        by_id[burn_id].append(parsed)
        properties_by_id.setdefault(burn_id, {str(key): value for key, value in properties.items()})
    if not by_id:
        raise ValueError(f"no valid burn geometries with property {id_property!r}")

    weights: list[dict[str, Any]] = []
    burn_units: list[dict[str, Any]] = []
    for burn_id in sorted(by_id):
        geometry_wgs84 = unary_union(by_id[burn_id])
        geometry_albers = transform(transformer.transform, geometry_wgs84)
        min_lon, min_lat, max_lon, max_lat = geometry_wgs84.bounds
        lat_indices = [
            index
            for index in range(len(lat))
            if max(lat_edges[index], lat_edges[index + 1]) >= min_lat
            and min(lat_edges[index], lat_edges[index + 1]) <= max_lat
        ]
        lon_indices = [
            index
            for index in range(len(lon))
            if max(lon_edges[index], lon_edges[index + 1]) >= min_lon
            and min(lon_edges[index], lon_edges[index + 1]) <= max_lon
        ]
        covered_area = 0.0
        selected_cells = 0
        for lat_index in lat_indices:
            for lon_index in lon_indices:
                cell_wgs84 = box(
                    min(lon_edges[lon_index], lon_edges[lon_index + 1]),
                    min(lat_edges[lat_index], lat_edges[lat_index + 1]),
                    max(lon_edges[lon_index], lon_edges[lon_index + 1]),
                    max(lat_edges[lat_index], lat_edges[lat_index + 1]),
                )
                cell_albers = transform(transformer.transform, cell_wgs84)
                cell_area = float(cell_albers.area)
                overlap_area = float(cell_albers.intersection(geometry_albers).area)
                # Reprojection can turn a shared boundary into sub-millimetre
                # numerical slivers. Do not publish those as selected cells.
                if overlap_area <= max(1e-6, cell_area * 1e-10):
                    continue
                weight = overlap_area / cell_area
                if not 0.0 < weight <= 1.0 + 1e-8:
                    raise RuntimeError("polygon-grid overlay produced an invalid area weight")
                covered_area += overlap_area
                selected_cells += 1
                weights.append(
                    {
                        "burn_id": burn_id,
                        "latitude_index": lat_index,
                        "longitude_index": lon_index,
                        "latitude": float(lat[lat_index]),
                        "longitude": float(lon[lon_index]),
                        "area_weight": min(1.0, float(weight)),
                        "overlap_hectares": overlap_area / 10_000.0,
                        "grid_cell_hectares": cell_area / 10_000.0,
                    }
                )
        polygon_area = float(geometry_albers.area)
        burn_units.append(
            {
                "burn_id": burn_id,
                "status": "ok" if selected_cells else "zero_coverage",
                "polygon_hectares": polygon_area / 10_000.0,
                "covered_hectares": covered_area / 10_000.0,
                "polygon_coverage_fraction": covered_area / polygon_area if polygon_area else 0.0,
                "selected_grid_cells": selected_cells,
                "properties": properties_by_id[burn_id],
                "failure_reason": None if selected_cells else "polygon_does_not_intersect_grid",
            }
        )
    return {
        "schema_version": 1,
        "source_crs": "EPSG:4326",
        "area_crs": "EPSG:3577 Australian Albers",
        "grid_shape": [len(lat), len(lon)],
        "burn_unit_count": len(burn_units),
        "covered_burn_unit_count": sum(item["status"] == "ok" for item in burn_units),
        "zero_coverage_burn_unit_count": sum(
            item["status"] == "zero_coverage" for item in burn_units
        ),
        "burn_units": burn_units,
        "weights": weights,
        "contract": (
            "area-weighted polygon-to-grid intersection; zero coverage fails explicitly and "
            "never falls back to the nearest grid centre"
        ),
    }


def aggregate_burn_unit_climatology(
    overlay: Mapping[str, Any],
    *,
    years: Sequence[int],
    metrics: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    """Aggregate annual grid metrics to burn units using intersection-area weights."""

    year_values = [int(value) for value in years]
    expected_shape = (len(year_values), *tuple(int(value) for value in overlay["grid_shape"]))
    arrays = {name: np.asarray(value, dtype=float) for name, value in metrics.items()}
    if not arrays:
        raise ValueError("at least one climatology metric is required")
    for name, values in arrays.items():
        if values.shape != expected_shape:
            raise ValueError(f"metric {name!r} has shape {values.shape}, expected {expected_shape}")

    weights_by_burn: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in overlay.get("weights", []):
        weights_by_burn[str(row["burn_id"])].append(dict(row))
    results: list[dict[str, Any]] = []
    for burn in overlay.get("burn_units", []):
        burn_id = str(burn["burn_id"])
        weight_rows = weights_by_burn.get(burn_id, [])
        if not weight_rows:
            results.append(
                {
                    "burn_id": burn_id,
                    "status": "zero_coverage",
                    "failure_reason": "polygon_does_not_intersect_grid",
                    "annual": [],
                }
            )
            continue
        annual: list[dict[str, Any]] = []
        for year_index, year in enumerate(year_values):
            values_by_metric: dict[str, float | None] = {}
            coverage_by_metric: dict[str, float] = {}
            for name, values in arrays.items():
                numerator = denominator = 0.0
                for row in weight_rows:
                    value = values[
                        year_index,
                        int(row["latitude_index"]),
                        int(row["longitude_index"]),
                    ]
                    if np.isfinite(value):
                        weight = float(row["overlap_hectares"])
                        numerator += weight * float(value)
                        denominator += weight
                values_by_metric[name] = numerator / denominator if denominator else None
                coverage_by_metric[name] = denominator / float(burn["covered_hectares"])
            annual.append(
                {
                    "year": year,
                    "metrics": values_by_metric,
                    "valid_area_fraction": coverage_by_metric,
                }
            )
        results.append(
            {
                "burn_id": burn_id,
                "status": "ok",
                "polygon_hectares": burn["polygon_hectares"],
                "covered_hectares": burn["covered_hectares"],
                "polygon_coverage_fraction": burn["polygon_coverage_fraction"],
                "annual": annual,
            }
        )
    return {
        "schema_version": 1,
        "years": year_values,
        "metric_names": sorted(arrays),
        "burn_units": results,
        "value_definition": "area-weighted mean over valid polygon-grid intersections",
    }
