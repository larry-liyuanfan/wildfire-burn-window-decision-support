"""Literature-derived fuel-moisture and fuel-level-wind inputs.

These functions close a model-input gap without pretending that gridded
meteorology is an on-site measurement.  Every caller receives the method,
parameters and validity guard needed to keep the proxy auditable.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from .models import Condition, Prescription

DERIVABLE_VARIABLES = {"fmc_surface_inside_pct", "wind_speed_ground_kmh"}


def viney_fmc_pct(
    temperature_c: Sequence[float] | np.ndarray,
    relative_humidity_pct: Sequence[float] | np.ndarray,
) -> np.ndarray:
    """Estimate eucalypt-litter FMC using Viney's empirical equation."""

    temperature = np.asarray(temperature_c, dtype=float)
    humidity = np.asarray(relative_humidity_pct, dtype=float)
    if np.any(temperature <= 0):
        raise ValueError("Viney FMC proxy requires temperature_c > 0")
    if np.any((humidity < 1) | (humidity > 100)):
        raise ValueError("relative_humidity_pct must be in [1, 100]")
    return (
        5.658
        + 0.04651 * humidity
        + 0.0003151 * humidity**3 / temperature
        - 0.184 * temperature**0.77
    )


def van_wagner_pickett_fmc_pct(
    temperature_c: Sequence[float] | np.ndarray,
    relative_humidity_pct: Sequence[float] | np.ndarray,
) -> np.ndarray:
    """Estimate equilibrium FMC with the Van Wagner--Pickett equation."""

    temperature = np.asarray(temperature_c, dtype=float)
    humidity = np.asarray(relative_humidity_pct, dtype=float)
    if np.any((humidity < 1) | (humidity > 100)):
        raise ValueError("relative_humidity_pct must be in [1, 100]")
    return (
        0.942 * humidity**0.679
        + 0.000499 * np.exp(0.1 * humidity)
        + 0.18 * (21.1 - temperature) * (1 - np.exp(-0.115 * humidity))
    )


def derive_fuel_input_arrays(
    *,
    temperature_c: Sequence[float] | np.ndarray,
    relative_humidity_pct: Sequence[float] | np.ndarray,
    wind_10m_kmh: Sequence[float] | np.ndarray,
    precipitation_mm: Sequence[float] | np.ndarray | None = None,
    wind_reduction_factor: float = 0.33,
    rain_guard_mm: float = 0.2,
) -> dict[str, Any]:
    """Return an FMC model ensemble and a 10-m-to-fuel-level wind scenario."""

    if not 0 < wind_reduction_factor <= 1:
        raise ValueError("wind_reduction_factor must be in (0, 1]")
    if rain_guard_mm < 0:
        raise ValueError("rain_guard_mm cannot be negative")
    temperature = np.asarray(temperature_c, dtype=float)
    humidity = np.asarray(relative_humidity_pct, dtype=float)
    wind = np.asarray(wind_10m_kmh, dtype=float)
    if temperature.shape != humidity.shape or temperature.shape != wind.shape:
        raise ValueError("fuel-input arrays have different shapes")
    if np.any(wind < 0):
        raise ValueError("wind_10m_kmh cannot be negative")
    viney = viney_fmc_pct(temperature, humidity)
    van_wagner = van_wagner_pickett_fmc_pct(temperature, humidity)
    lower = np.minimum(viney, van_wagner)
    upper = np.maximum(viney, van_wagner)
    midpoint = (viney + van_wagner) / 2.0
    rain_affected = np.zeros(temperature.shape, dtype=bool)
    if precipitation_mm is not None:
        rain = np.asarray(precipitation_mm, dtype=float)
        if rain.shape != temperature.shape:
            raise ValueError("precipitation_mm has a different shape")
        if np.any(rain < 0):
            raise ValueError("precipitation_mm cannot be negative")
        rain_affected = rain > rain_guard_mm
        midpoint = np.where(rain_affected, np.nan, midpoint)
        lower = np.where(rain_affected, np.nan, lower)
        upper = np.where(rain_affected, np.nan, upper)
    return {
        "fmc_surface_inside_pct": midpoint,
        "fmc_model_lower_pct": lower,
        "fmc_model_upper_pct": upper,
        "fmc_viney_pct": viney,
        "fmc_van_wagner_pickett_pct": van_wagner,
        "wind_speed_ground_kmh": wind * wind_reduction_factor,
        "rain_affected": rain_affected,
        "provenance": {
            "fmc_models": ["Viney-1991", "Van-Wagner-Pickett-1985"],
            "fmc_ensemble": "arithmetic midpoint with model-spread interval",
            "fmc_validity": "dry fine dead fuel; rain-affected hours are missing",
            "wind_method": "10-m open wind multiplied by an explicit wind-reduction factor",
            "wind_reduction_factor": wind_reduction_factor,
            "rain_guard_mm": rain_guard_mm,
            "observed_on_site": False,
        },
    }


def promote_derived_conditions(prescription: Prescription) -> Prescription:
    """Promote only the two implemented proxies from unmapped to provisional."""

    rule = prescription.model_copy(deep=True)
    promoted: list[Condition] = []
    for condition in rule.conditions:
        if condition.variable in DERIVABLE_VARIABLES and condition.operational_status == "unmapped":
            condition.operational_status = "provisional"
        promoted.append(condition)
    rule.conditions = promoted
    rule.metadata = {
        **rule.metadata,
        "derived_proxy_variables": sorted(
            condition.variable
            for condition in promoted
            if condition.variable in DERIVABLE_VARIABLES
        ),
    }
    return rule


def add_xarray_fuel_inputs(
    dataset: object,
    *,
    wind_reduction_factor: float = 0.33,
    rain_guard_mm: float = 0.2,
) -> tuple[object, dict[str, Any], list[str]]:
    """Attach lazy Xarray proxy arrays while preserving source coordinates."""

    required = {"temperature_c", "relative_humidity_pct", "wind_speed_kmh"}
    missing = sorted(required - set(dataset.data_vars))
    if missing:
        raise ValueError(f"cannot derive fuel inputs; dataset lacks {missing}")
    temperature = dataset["temperature_c"]
    humidity = dataset["relative_humidity_pct"]
    viney = (
        5.658
        + 0.04651 * humidity
        + 0.0003151 * humidity**3 / temperature
        - 0.184 * temperature**0.77
    )
    van_wagner = (
        0.942 * humidity**0.679
        + 0.000499 * np.exp(0.1 * humidity)
        + 0.18 * (21.1 - temperature) * (1 - np.exp(-0.115 * humidity))
    )
    midpoint = (viney + van_wagner) / 2.0
    warnings = [
        "fuel moisture is a dry-fuel meteorological proxy, not an on-site meter reading",
        "fuel-level wind uses an explicit literature wind-reduction scenario, not site calibration",
    ]
    if "precipitation_mm" in dataset.data_vars:
        midpoint = midpoint.where(dataset["precipitation_mm"] <= rain_guard_mm)
    else:
        warnings.append("precipitation field absent; FMC rain guard was not applied")
    result = dataset.copy()
    result["fmc_surface_inside_pct"] = midpoint
    result["fmc_surface_inside_pct"].attrs = {
        "units": "%",
        "method": "midpoint(Viney-1991, Van-Wagner-Pickett-1985)",
        "observed_on_site": "false",
    }
    result["wind_speed_ground_kmh"] = result["wind_speed_kmh"] * wind_reduction_factor
    result["wind_speed_ground_kmh"].attrs = {
        "units": "km/h",
        "method": "10-m open wind multiplied by wind-reduction factor",
        "wind_reduction_factor": wind_reduction_factor,
        "observed_on_site": "false",
    }
    provenance = {
        "variables": ["fmc_surface_inside_pct", "wind_speed_ground_kmh"],
        "fmc_models": ["Viney-1991", "Van-Wagner-Pickett-1985"],
        "fmc_ensemble": "arithmetic midpoint",
        "fmc_rain_guard_mm": rain_guard_mm if "precipitation_mm" in dataset.data_vars else None,
        "wind_reduction_factor": wind_reduction_factor,
        "observed_on_site": False,
    }
    return result, provenance, warnings
