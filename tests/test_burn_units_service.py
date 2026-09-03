from __future__ import annotations

import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from burnwindows.agent import ModelStudioFunctionPlanner
from burnwindows.burn_units import (
    aggregate_burn_unit_climatology,
    build_area_weighted_overlay,
    coordinate_edges,
)
from burnwindows.service import create_app


def _feature(burn_id: str, coordinates: list[list[float]]) -> dict:
    return {
        "type": "Feature",
        "properties": {"TREAT_NO": burn_id, "TREAT_NAME": f"Burn {burn_id}"},
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
    }


def test_coordinate_edges_require_monotonic_grid() -> None:
    assert coordinate_edges([0.0, 2.0]).tolist() == [-1.0, 1.0, 3.0]
    assert coordinate_edges([2.0, 0.0]).tolist() == [3.0, 1.0, -1.0]


def test_area_weighted_overlay_and_zero_coverage_are_explicit() -> None:
    features = {
        "type": "FeatureCollection",
        "features": [
            _feature(
                "burn-1",
                [
                    [143.98, -37.02],
                    [144.02, -37.02],
                    [144.02, -36.98],
                    [143.98, -36.98],
                    [143.98, -37.02],
                ],
            ),
            _feature(
                "burn-outside",
                [
                    [150.0, -30.0],
                    [150.1, -30.0],
                    [150.1, -29.9],
                    [150.0, -29.9],
                    [150.0, -30.0],
                ],
            ),
        ],
    }
    overlay = build_area_weighted_overlay(
        features,
        latitude=[-37.0, -36.96],
        longitude=[144.0, 144.04],
    )
    by_id = {row["burn_id"]: row for row in overlay["burn_units"]}
    assert by_id["burn-1"]["status"] == "ok"
    assert by_id["burn-1"]["selected_grid_cells"] == 1
    assert overlay["weights"][0]["area_weight"] == pytest.approx(1.0, rel=1e-4)
    assert by_id["burn-outside"]["status"] == "zero_coverage"
    assert by_id["burn-outside"]["failure_reason"] == "polygon_does_not_intersect_grid"


def test_burn_unit_climatology_uses_area_weights_and_reports_missing() -> None:
    overlay = {
        "grid_shape": [1, 2],
        "burn_units": [
            {
                "burn_id": "b1",
                "polygon_hectares": 20.0,
                "covered_hectares": 20.0,
                "polygon_coverage_fraction": 1.0,
            },
            {
                "burn_id": "b2",
                "polygon_hectares": 10.0,
                "covered_hectares": 0.0,
                "polygon_coverage_fraction": 0.0,
            },
        ],
        "weights": [
            {"burn_id": "b1", "latitude_index": 0, "longitude_index": 0, "overlap_hectares": 5.0},
            {"burn_id": "b1", "latitude_index": 0, "longitude_index": 1, "overlap_hectares": 15.0},
        ],
    }
    result = aggregate_burn_unit_climatology(
        overlay,
        years=[2020, 2021],
        metrics={"window_frequency": np.asarray([[[1.0, 3.0]], [[2.0, 4.0]]])},
    )
    by_id = {row["burn_id"]: row for row in result["burn_units"]}
    assert by_id["b1"]["annual"][0]["metrics"]["window_frequency"] == 2.5
    assert by_id["b1"]["annual"][1]["metrics"]["window_frequency"] == 3.5
    assert by_id["b2"]["status"] == "zero_coverage"


def test_tool_service_rejects_undeclared_fields_and_records_trace() -> None:
    client = TestClient(create_app())
    tools = client.get("/api/tools")
    assert tools.status_code == 200
    assert len(tools.json()["tools"]) == 7
    payload = {
        "times": ["2026-01-01T00:00:00", "2026-01-01T01:00:00"],
        "data": {"temperature_c": [20, 20], "relative_humidity_pct": [50, 50]},
        "prescription": {
            "burn_class": "fixture",
            "conditions": [
                {
                    "field": "Temperature",
                    "variable": "temperature_c",
                    "unit": "C",
                    "lower": {"value": 10, "inclusive": True},
                    "upper": {"value": 30, "inclusive": True},
                    "source_text": "10 to 30 C",
                },
                {
                    "field": "RelativeHumidity",
                    "variable": "relative_humidity_pct",
                    "unit": "%",
                    "lower": {"value": 30, "inclusive": True},
                    "upper": {"value": 70, "inclusive": True},
                    "source_text": "30 to 70 percent",
                },
            ],
        },
        "data_version": "fixture-v1",
    }
    response = client.post(
        "/api/tools/find_burn_windows:invoke", json={"arguments": payload}
    )
    assert response.status_code == 200
    assert response.json()["trace_id"]
    assert response.json()["result"]["suitable_hours"] == 2
    payload["arbitrary_dask_expression"] = "drop all constraints"
    rejected = client.post(
        "/api/tools/find_burn_windows:invoke", json={"arguments": payload}
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["reason"] == "undeclared_fields"


def test_climatology_job_is_async_and_catalog_scoped() -> None:
    client = TestClient(create_app(climatology_runner=lambda request: {"artifact_id": request["artifact_id"]}))
    submitted = client.post(
        "/api/jobs/burn-unit-climatology",
        json={"artifact_id": "public-compact-v1", "burn_ids": ["b1"], "metrics": ["frequency"]},
    )
    assert submitted.status_code == 202
    job_id = submitted.json()["job_id"]
    for _ in range(50):
        row = client.get(f"/api/jobs/{job_id}").json()
        if row["status"] == "completed":
            break
        time.sleep(0.01)
    assert row["status"] == "completed"
    assert row["result"]["artifact_id"] == "public-compact-v1"


def test_model_studio_planner_requires_environment(monkeypatch) -> None:
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_STUDIO_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="required"):
        ModelStudioFunctionPlanner().plan("Find windows")
