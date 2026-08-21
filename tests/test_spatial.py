import json

import numpy as np
import xarray as xr

from burnwindows.spatial import geometry_mask, subset_rectilinear_geojson


def _polygon() -> dict[str, object]:
    return {
        "type": "Polygon",
        "coordinates": [
            [[-0.4, -0.4], [2.6, -0.4], [2.6, 2.6], [-0.4, 2.6], [-0.4, -0.4]],
            [[0.6, 0.6], [1.4, 0.6], [1.4, 1.4], [0.6, 1.4], [0.6, 0.6]],
        ],
    }


def test_geometry_mask_handles_exterior_and_hole() -> None:
    result = geometry_mask(np.arange(4), np.arange(4), _polygon())

    assert result.sum() == 8
    assert not result[1, 1]
    assert result[0, 0]
    assert result[2, 2]


def test_subset_stacks_only_selected_grid_cells(tmp_path) -> None:
    dataset = xr.Dataset(
        {"temperature_c": (("time", "latitude", "longitude"), np.ones((2, 4, 4)))},
        coords={"time": [0, 1], "latitude": np.arange(4), "longitude": np.arange(4)},
    )
    boundary = tmp_path / "region.geojson"
    boundary.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"DISTRICT_NAME": "fixture"},
                        "geometry": _polygon(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    subset, metadata = subset_rectilinear_geojson(dataset, boundary)

    assert subset.sizes == {"time": 2, "spatial_cell": 8}
    assert metadata["selected_grid_cells"] == 8
    assert metadata["total_grid_cells"] == 16
    assert metadata["feature_properties"]["DISTRICT_NAME"] == "fixture"


def test_subset_rejects_feature_collections_with_ambiguous_scope(tmp_path) -> None:
    dataset = xr.Dataset(coords={"latitude": [0], "longitude": [0]})
    boundary = tmp_path / "ambiguous.geojson"
    boundary.write_text(
        json.dumps({"type": "FeatureCollection", "features": [{}, {}]}),
        encoding="utf-8",
    )

    try:
        subset_rectilinear_geojson(dataset, boundary)
    except ValueError as exc:
        assert "exactly one feature" in str(exc)
    else:
        raise AssertionError("ambiguous region scope was accepted")
