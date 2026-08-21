"""Conservative adapters for public reanalysis engineering preflights."""

from __future__ import annotations

from typing import Any

import numpy as np

from .models import Bound, Condition, Prescription

HISTORICAL_WEATHER_SCREEN_SOURCE = (
    "https://www.ffm.vic.gov.au/__data/assets/pdf_file/0015/531222/"
    "Report-of-the-Inquiry-into-the-2002-2003-Victorian-Bushfires.pdf"
)


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


def historical_weather_screen_prescription() -> Prescription:
    """Return a deliberately incomplete, public weather-only screening rule.

    The 2003 Victorian Bushfires Inquiry records Tolhurst's historical weather
    criteria among a larger prescription that also includes FFDI, next-day
    FFDI, FFFI and rainfall-history constraints.  Only the three variables
    directly observable in the public ERA5 adapter are compiled here.  The
    unresolved map makes the omitted criteria machine-visible, so callers must
    describe the result as a necessary-condition screen rather than a burn
    window or operational recommendation.
    """

    return Prescription(
        burn_class="historical-tolhurst-weather-screen",
        source=HISTORICAL_WEATHER_SCREEN_SOURCE,
        conditions=[
            Condition(
                field="Temperature",
                variable="temperature_c",
                unit="degC",
                lower=Bound(value=14.0, inclusive=False),
                upper=Bound(value=25.0, inclusive=False),
                source_text=">14 and <25",
                operational_status="provisional",
            ),
            Condition(
                field="RelativeHumidity",
                variable="relative_humidity_pct",
                unit="%",
                lower=Bound(value=35.0, inclusive=False),
                upper=Bound(value=70.0, inclusive=False),
                source_text=">35 and <70",
                operational_status="provisional",
            ),
            Condition(
                field="WindSpeed",
                variable="wind_speed_kmh",
                unit="km/h",
                upper=Bound(value=20.0, inclusive=False),
                source_text="<20",
                operational_status="provisional",
            ),
        ],
        unresolved={
            "FFDI": "historical criterion <10; not derived by the public ERA5 adapter",
            "next_day_FFDI": "historical criterion <15; not derived by the public ERA5 adapter",
            "FFFI": "historical criterion 6-10; not derived by the public ERA5 adapter",
            "rain_history": "day/previous-two-day criterion; not implemented without validated accumulation semantics",
            "fuel_moisture_and_burn_plan": "site-specific operational inputs are unavailable",
        },
        metadata={
            "evidence_kind": "historical-public-necessary-condition-screen",
            "operational_use": "prohibited",
        },
    )
