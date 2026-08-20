from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from burnwindows.public_reanalysis import (
    derive_public_fire_weather_fields,
    relative_humidity_from_dewpoint,
)


def test_relative_humidity_is_bounded_and_reaches_saturation() -> None:
    humidity = relative_humidity_from_dewpoint(
        np.asarray([293.15, 303.15]),
        np.asarray([293.15, 293.15]),
    )
    assert humidity[0] == pytest.approx(100.0)
    assert 0.0 < humidity[1] < 100.0


def test_public_derivation_declares_units_and_refuses_to_invent_indices() -> None:
    dataset = xr.Dataset(
        {
            "2m_temperature": ("time", [293.15]),
            "2m_dewpoint_temperature": ("time", [283.15]),
            "10m_u_component_of_wind": ("time", [3.0]),
            "10m_v_component_of_wind": ("time", [4.0]),
            "total_precipitation": ("time", [0.002]),
        },
        coords={"time": ["2024-02-01T00:00:00"]},
    )
    derived = derive_public_fire_weather_fields(dataset)
    assert derived["temperature_c"].item() == pytest.approx(20.0)
    assert derived["wind_speed_kmh"].item() == pytest.approx(18.0)
    assert derived["precipitation_mm"].item() == pytest.approx(2.0)
    assert "FFDI" not in derived and "KBDI" not in derived
    assert derived.attrs["not_vicclim6"] == "true"


def test_public_preflight_clones_linked_worktrees_without_shared_alternates() -> None:
    script = (
        Path(__file__).parents[1] / "spartan" / "run_arco_era5_preflight.sbatch"
    ).read_text(encoding="utf-8")
    assert 'git clone --no-local --no-checkout "${SOURCE_REPO}" "${CODE_ROOT}"' in script
    assert "git clone --shared" not in script
