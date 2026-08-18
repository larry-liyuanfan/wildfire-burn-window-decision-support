from __future__ import annotations

import numpy as np
import xarray as xr

from burnwindows.io import ensure_hourly_grid, evaluate_xarray, normalise_dataset


def test_declared_units_are_converted() -> None:
    dataset = xr.Dataset(
        {
            "T_SFC": ("time", [293.15], {"units": "K"}),
            "RHSFC": ("time", [0.5], {"units": "fraction"}),
            "WMAG": ("time", [10.0], {"units": "m/s"}),
        },
        coords={"time": ["2026-01-01"]},
    )
    result, warnings = normalise_dataset(dataset)
    assert not warnings
    assert np.isclose(result.temperature_c.item(), 20)
    assert np.isclose(result.relative_humidity_pct.item(), 50)
    assert np.isclose(result.wind_speed_kmh.item(), 36)


def test_xarray_and_numpy_logic_match(core_prescription) -> None:
    dataset = xr.Dataset(
        {
            "temperature_c": ("time", [15, 20, 26]),
            "relative_humidity_pct": ("time", [35, 60, 50]),
        },
        coords={"time": np.arange("2026-01-01", "2026-01-04", dtype="datetime64[D]")},
    ).chunk({"time": 2})
    suitable, _, _ = evaluate_xarray(dataset, core_prescription)
    assert suitable.compute().values.tolist() == [True, True, False]


def test_hourly_grid_inserts_missing_timestamp() -> None:
    dataset = xr.Dataset(
        {"temperature_c": ("time", [20.0, 20.0])},
        coords={"time": ["2026-01-01T00:00", "2026-01-01T02:00"]},
    )
    result = ensure_hourly_grid(dataset)
    assert result.sizes["time"] == 3
    assert np.isnan(result.temperature_c.values[1])
