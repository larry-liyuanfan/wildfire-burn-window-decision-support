from __future__ import annotations

import numpy as np
import pandas as pd

from burnwindows.public_reanalysis import historical_weather_screen_prescription
from burnwindows.weather_screen import continuous_run_counts, summarize_weather_screen


def test_historical_screen_keeps_missing_operational_constraints_explicit() -> None:
    rule = historical_weather_screen_prescription()
    assert len(rule.conditions) == 3
    assert {"FFDI", "next_day_FFDI", "FFFI", "rain_history"} <= set(rule.unresolved)
    assert rule.metadata["operational_use"] == "prohibited"


def test_continuous_run_counts_operate_per_grid_cell() -> None:
    mask = np.asarray(
        [
            [[True, False]],
            [[True, True]],
            [[False, True]],
            [[True, True]],
            [[True, True]],
            [[True, False]],
        ]
    )
    assert continuous_run_counts(mask) == {"2": 3, "4": 1, "6": 0}


def test_weather_screen_summary_reports_months_and_limiting_factors() -> None:
    times = pd.date_range("2024-01-31T23:00:00", periods=4, freq="h")
    suitable = np.asarray([[[True]], [[True]], [[False]], [[True]]])
    masks = {
        "temperature": np.asarray([[[True]], [[True]], [[False]], [[True]]]),
        "wind": np.asarray([[[True]], [[False]], [[True]], [[True]]]),
    }
    result = summarize_weather_screen(suitable, times, masks)
    assert result["screened_cell_hours"] == 3
    assert set(result["monthly"]) == {"2024-01", "2024-02"}
    assert result["limiting_factors"][0]["failure_count"] == 1
