"""Conservative adapters for public reanalysis engineering preflights."""

from __future__ import annotations

from typing import Any

import numpy as np


def relative_humidity_from_dewpoint(
    temperature_kelvin: Any,
    dewpoint_kelvin: Any,
) -> Any:
    """Derive bounded relative humidity using the Magnus approximation."""

    temperature_c = temperature_kelvin - 273.15
    dewpoint_c = dewpoint_kelvin - 273.15
    exponent = 17.625 * dewpoint_c / (243.04 + dewpoint_c) - 17.625 * temperature_c / (
        243.04 + temperature_c
    )
    return (100.0 * np.exp(exponent)).clip(min=0.0, max=100.0)


def derive_public_fire_weather_fields(dataset: Any) -> Any:
    """Derive declared-unit fields without inventing FFDI or KBDI.

    The caller is responsible for verifying source accumulation semantics before
    using precipitation in a drought index.  This adapter intentionally emits
    no FFDI, drought factor or KBDI field.
    """

    required = {
        "2m_temperature",
        "2m_dewpoint_temperature",
        "10m_u_component_of_wind",
        "10m_v_component_of_wind",
        "total_precipitation",
    }
    missing = sorted(required - set(dataset.data_vars))
    if missing:
        raise KeyError(f"public reanalysis is missing required variables: {missing}")
    result = dataset[[*sorted(required)]].copy()
    result["temperature_c"] = result["2m_temperature"] - 273.15
    result["temperature_c"].attrs = {"units": "degC", "derivation": "kelvin - 273.15"}
    result["relative_humidity_pct"] = relative_humidity_from_dewpoint(
        result["2m_temperature"], result["2m_dewpoint_temperature"]
    )
    result["relative_humidity_pct"].attrs = {
        "units": "%",
        "derivation": "Magnus approximation from 2m temperature and dewpoint",
    }
    result["wind_speed_kmh"] = (
        np.hypot(result["10m_u_component_of_wind"], result["10m_v_component_of_wind"])
        * 3.6
    )
    result["wind_speed_kmh"].attrs = {
        "units": "km/h",
        "derivation": "hypot(10m_u, 10m_v) * 3.6",
    }
    result["precipitation_mm"] = result["total_precipitation"] * 1000.0
    result["precipitation_mm"].attrs = {
        "units": "mm",
        "derivation": "metres * 1000; source accumulation semantics require separate validation",
    }
    result.attrs.update(
        {
            "data_kind": "real-public-reanalysis-engineering-preflight",
            "not_vicclim6": "true",
            "ffdi_kbdi_status": "not-derived",
        }
    )
    return result
