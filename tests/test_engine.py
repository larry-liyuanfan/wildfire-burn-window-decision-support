from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from burnwindows.engine import (
    evaluate_condition,
    evaluate_prescription,
    extract_windows,
    limiting_factors,
)
from burnwindows.models import Bound, Condition, MissingPolicy, Prescription


def test_inclusive_and_exclusive_boundaries() -> None:
    inclusive = Condition(field="x", variable="x", lower=Bound(value=1), upper=Bound(value=2), source_text="1-2")
    strict = Condition(field="x", variable="x", upper=Bound(value=2, inclusive=False), source_text="<2")
    values = np.array([1, 2, np.nan])
    assert evaluate_condition(values, inclusive).tolist() == [True, True, False]
    assert evaluate_condition(values, strict).tolist() == [True, False, False]


def test_missing_variable_policies(core_prescription: Prescription) -> None:
    data = {"temperature_c": np.array([20.0])}
    with pytest.raises(KeyError):
        evaluate_prescription(data, core_prescription)
    failed, _, _ = evaluate_prescription(data, core_prescription, missing_policy=MissingPolicy.FAIL)
    ignored, _, _ = evaluate_prescription(data, core_prescription, missing_policy=MissingPolicy.IGNORE)
    assert not failed[0]
    assert ignored[0]


def test_seasonal_rule_is_neutral_outside_season() -> None:
    prescription = Prescription(
        burn_class="seasonal",
        conditions=[
            Condition(field="KBDI", variable="KBDI", upper=Bound(value=20), season="spring", source_text="<=20")
        ],
    )
    result, _, _ = evaluate_prescription(
        {"KBDI": np.array([30.0, 30.0])},
        prescription,
        times=["2026-09-01", "2026-03-01"],
    )
    assert result.tolist() == [False, True]


def test_continuous_windows_extract_two_four_and_six_hours() -> None:
    times = pd.date_range("2026-01-01", periods=10, freq="h")
    mask = [False, True, True, True, True, True, True, False, True, True]
    assert [item.duration_hours for item in extract_windows(mask, times, min_duration_hours=2)] == [6, 2]
    assert [item.duration_hours for item in extract_windows(mask, times, min_duration_hours=4)] == [6]
    assert [item.duration_hours for item in extract_windows(mask, times, min_duration_hours=6)] == [6]


def test_irregular_time_gap_splits_window() -> None:
    times = pd.to_datetime(["2026-01-01T00:00", "2026-01-01T01:00", "2026-01-01T03:00", "2026-01-01T04:00"])
    windows = extract_windows([True] * 4, times, min_duration_hours=2)
    assert [item.duration_hours for item in windows] == [2, 2]


def test_limiting_factor_reports_exclusive_failures() -> None:
    result = limiting_factors(
        {
            "temperature": np.array([True, False, False]),
            "humidity": np.array([True, True, False]),
        }
    )
    assert result[0]["constraint"] == "temperature"
    assert result[0]["exclusive_failure_count"] == 1

