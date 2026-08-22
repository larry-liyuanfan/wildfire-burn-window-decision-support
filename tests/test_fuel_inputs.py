import numpy as np
import pytest

from burnwindows.fuel_inputs import (
    derive_fuel_input_arrays,
    promote_derived_conditions,
    van_wagner_pickett_fmc_pct,
    viney_fmc_pct,
)
from burnwindows.models import Bound, Condition, Prescription
from burnwindows.tools import derive_fuel_inputs, tool_schemas


def test_fmc_ensemble_and_rain_guard_are_deterministic() -> None:
    result = derive_fuel_input_arrays(
        temperature_c=[20.0, 25.0],
        relative_humidity_pct=[50.0, 40.0],
        wind_10m_kmh=[30.0, 20.0],
        precipitation_mm=[0.0, 0.3],
        wind_reduction_factor=0.33,
    )
    viney = viney_fmc_pct([20.0], [50.0])[0]
    van_wagner = van_wagner_pickett_fmc_pct([20.0], [50.0])[0]
    assert result["fmc_surface_inside_pct"][0] == pytest.approx((viney + van_wagner) / 2)
    assert np.isnan(result["fmc_surface_inside_pct"][1])
    assert result["wind_speed_ground_kmh"].tolist() == pytest.approx([9.9, 6.6])
    assert result["provenance"]["observed_on_site"] is False


def test_typed_fuel_tool_serialises_guarded_values_as_null() -> None:
    response = derive_fuel_inputs(
        temperature_c=[20.0, 25.0],
        relative_humidity_pct=[50.0, 40.0],
        wind_10m_kmh=[30.0, 20.0],
        precipitation_mm=[0.0, 0.3],
    )
    assert response.status == "partial"
    assert response.result["fmc_surface_inside_pct"][1] is None
    assert "derive_fuel_inputs" in tool_schemas()


def test_promote_only_implemented_proxy_conditions() -> None:
    rule = Prescription(
        burn_class="fixture",
        conditions=[
            Condition(
                field="FMCSurfaceInside",
                variable="fmc_surface_inside_pct",
                upper=Bound(value=16),
                source_text="<=16",
                operational_status="unmapped",
            ),
            Condition(
                field="FMCBark",
                variable="fmc_bark_pct",
                upper=Bound(value=20),
                source_text="<=20",
                operational_status="unmapped",
            ),
            Condition(
                field="WindSpeedGround",
                variable="wind_speed_ground_kmh",
                upper=Bound(value=10),
                source_text="<=10",
                operational_status="unmapped",
            ),
        ],
    )
    promoted = promote_derived_conditions(rule)
    assert [item.operational_status for item in promoted.conditions] == [
        "provisional",
        "unmapped",
        "provisional",
    ]
    assert rule.conditions[0].operational_status == "unmapped"


def test_fmc_rejects_non_positive_temperature() -> None:
    with pytest.raises(ValueError, match="temperature_c"):
        viney_fmc_pct([0.0], [50.0])
