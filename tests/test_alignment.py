from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from burnwindows.alignment import (
    align_daily_dataarray,
    align_daily_to_hourly,
    normalise_times_to_utc,
)


def test_default_alignment_has_no_same_day_lookahead() -> None:
    daily_times = pd.date_range("2026-01-01", periods=2, freq="D")
    hourly = pd.date_range("2026-01-01", periods=49, freq="h")
    aligned = align_daily_to_hourly(daily_times, [10, 20], hourly)
    assert np.isnan(aligned[23])
    assert aligned[24] == 10
    assert aligned[47] == 10
    assert aligned[48] == 20


def test_documented_availability_time_can_use_zero_lag() -> None:
    daily_times = pd.date_range("2026-01-01", periods=1, freq="D")
    hourly = pd.date_range("2026-01-01", periods=2, freq="h")
    aligned = align_daily_to_hourly(daily_times, [10], hourly, availability_lag_hours=0)
    assert aligned.tolist() == [10, 10]


def test_stale_daily_value_becomes_missing() -> None:
    aligned = align_daily_to_hourly(
        ["2026-01-01"],
        [10],
        ["2026-01-04"],
        availability_lag_hours=0,
        max_age_hours=48,
    )
    assert np.isnan(aligned[0])


def test_duplicate_source_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        align_daily_to_hourly(
            ["2026-01-01", "2026-01-01"],
            [10, 20],
            ["2026-01-02"],
        )


def test_xarray_adapter_uses_same_availability_boundary() -> None:
    daily = xr.DataArray(
        [10.0, 20.0],
        dims="time",
        coords={"time": pd.date_range("2026-01-01", periods=2, freq="D")},
    )
    target = pd.date_range("2026-01-01T23:00", periods=3, freq="h")
    aligned = align_daily_dataarray(daily, target)
    assert np.isnan(aligned.values[0])
    assert aligned.values[1] == 10
    assert aligned.values[2] == 10


def test_ambiguous_dst_wall_time_is_rejected() -> None:
    with pytest.raises(ValueError):
        normalise_times_to_utc(
            ["2026-04-05T02:30"], source_timezone="Australia/Melbourne"
        )
