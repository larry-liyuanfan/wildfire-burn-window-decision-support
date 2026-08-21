from __future__ import annotations

import numpy as np
import xarray as xr

from burnwindows.io import (
    ensure_hourly_grid,
    evaluate_xarray,
    normalise_dataset,
    open_vicclim6_period,
)


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


def test_actual_vicclim6_aliases_and_knots_are_normalised() -> None:
    dataset = xr.Dataset(
        {
            "T_SFC": ("time", [20.0], {"units": "C"}),
            "RH_SFC": ("time", [50.0], {"units": "%"}),
            "Wind_Mag_SFC": ("time", [10.0], {"units": "kts"}),
        },
        coords={"time": ["2026-01-01"]},
    )

    result, warnings = normalise_dataset(dataset)

    assert not warnings
    assert result.relative_humidity_pct.item() == 50.0
    assert np.isclose(result.wind_speed_kmh.item(), 18.52)
    assert result.wind_speed_kmh.attrs["units"] == "km/h"


def test_vicclim6_period_loader_uses_previous_daily_value_without_lookahead(tmp_path) -> None:
    hourly_time = np.arange(
        "2026-01-01T00", "2026-01-01T03", dtype="datetime64[h]"
    )
    grid = {"latitude": [-37.0], "longitude": [145.0]}
    hourly_families = {
        "WRFV6_TSFC1972-2024": ("T_SFC", "C", 20.0),
        "WRFV6_RHSFC1972-2024": ("RH_SFC", "%", 50.0),
        "WRFV6_WMAG1972-2024": ("Wind_Mag_SFC", "kts", 10.0),
        "WRFV6_FFDI1972-2024": ("FFDI", "", 15.0),
    }
    for family, (variable, unit, value) in hourly_families.items():
        target = tmp_path / family / "2026" / "01"
        target.mkdir(parents=True)
        xr.Dataset(
            {
                variable: (
                    ("time", "latitude", "longitude"),
                    np.full((3, 1, 1), value),
                    {"units": unit},
                )
            },
            coords={"time": hourly_time, **grid},
        ).to_netcdf(target / f"{variable}.nc")

    daily_families = {
        "WRFV6_KBDI1972-2024": "KBDI-AWAP",
        "WRFV6_DF1972-2024": "DF",
    }
    for family, variable in daily_families.items():
        for year, month, time, value in (
            (2025, 12, "2025-12-31", 10.0),
            (2026, 1, "2026-01-01", 20.0),
        ):
            target = tmp_path / family / str(year) / f"{month:02d}"
            target.mkdir(parents=True)
            xr.Dataset(
                {
                    variable: (
                        ("time", "latitude", "longitude"),
                        np.full((1, 1, 1), value),
                    )
                },
                coords={"time": [time], **grid},
            ).to_netcdf(target / f"{variable}.nc")

    dataset = open_vicclim6_period(
        tmp_path,
        start="2026-01-01T00:00",
        end="2026-01-01T02:00",
        chunks={"time": 2},
    )
    result, warnings = normalise_dataset(dataset)

    assert not warnings
    assert result.sizes == {"time": 3, "latitude": 1, "longitude": 1}
    assert result.KBDI.compute().values[:, 0, 0].tolist() == [10.0, 10.0, 10.0]
    assert result.FFDI.compute().values[:, 0, 0].tolist() == [15.0, 15.0, 15.0]
    assert np.allclose(result.wind_speed_kmh.compute().values, 18.52)


def test_vicclim6_month_pilot_is_exact_sha_and_partial_rule_gated() -> None:
    from pathlib import Path

    script = (
        Path(__file__).parents[1] / "spartan" / "run_vicclim6_month_pilot.sbatch"
    ).read_text(encoding="utf-8")

    assert '${FLARE_GIT_SHA:?Pin the pushed commit to execute}' in script
    assert '--backend vicclim6' in script
    assert '--missing-policy error' in script
    assert '--include-unmapped' not in script
