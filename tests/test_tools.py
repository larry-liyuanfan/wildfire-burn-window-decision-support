from __future__ import annotations

import pandas as pd

from burnwindows.tools import (
    compare_threshold_scenarios,
    explain_limiting_factors,
    find_burn_windows,
    get_region_trend,
    tool_schemas,
)


def test_find_burn_windows_returns_stable_envelope(core_prescription) -> None:
    times = pd.date_range("2026-01-01", periods=4, freq="h")
    response = find_burn_windows(
        times=times,
        data={"temperature_c": [20, 20, 30, 20], "relative_humidity_pct": [50] * 4},
        prescription=core_prescription,
        min_duration_hours=2,
        data_version="fixture-v1",
    )
    assert response.status == "ok"
    assert response.data_version == "fixture-v1"
    assert response.result["suitable_hours"] == 3
    assert len(response.result["windows"]) == 1


def test_explain_limiting_factors_is_deterministic(core_prescription) -> None:
    payload = {
        "times": pd.date_range("2026-01-01", periods=3, freq="h"),
        "data": {"temperature_c": [10, 20, 30], "relative_humidity_pct": [50, 70, 50]},
        "prescription": core_prescription,
    }
    assert explain_limiting_factors(**payload).model_dump() == explain_limiting_factors(**payload).model_dump()


def test_threshold_scenario_widens_temperature_range(core_prescription) -> None:
    response = compare_threshold_scenarios(
        times=pd.date_range("2026-01-01", periods=3, freq="h"),
        data={"temperature_c": [13, 20, 27], "relative_humidity_pct": [50, 50, 50]},
        prescription=core_prescription,
        scenarios={"wider": {"Temperature": 3}},
    )
    rates = {item["scenario"]: item["suitable_rate"] for item in response.result["scenarios"]}
    assert rates["wider"] > rates["baseline"]


def test_region_trend_reports_known_linear_slope() -> None:
    response = get_region_trend(
        years=[2020, 2021, 2022, 2023],
        suitable_rates=[0.1, 0.2, 0.3, 0.4],
        region="test",
        bootstrap_samples=20,
    )
    assert abs(response.result["slope_per_year"] - 0.1) < 1e-12


def test_all_five_tools_publish_json_schema() -> None:
    schemas = tool_schemas()
    assert set(schemas) == {
        "find_burn_windows",
        "explain_limiting_factors",
        "compare_threshold_scenarios",
        "get_region_trend",
        "optimize_burn_schedule",
    }
    assert all(schema["type"] == "object" for schema in schemas.values())
