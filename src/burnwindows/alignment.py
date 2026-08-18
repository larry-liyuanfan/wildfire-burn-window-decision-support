"""Frequency alignment with explicit data-availability semantics."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd


def normalise_times_to_utc(
    values: Iterable[object], *, source_timezone: str = "UTC"
) -> pd.DatetimeIndex:
    """Make timezone assumptions explicit and reject ambiguous/nonexistent DST times."""

    index = pd.DatetimeIndex(values)
    if index.tz is None:
        index = index.tz_localize(source_timezone, ambiguous="raise", nonexistent="raise")
    return index.tz_convert("UTC")


def align_daily_to_hourly(
    daily_times: Iterable[object],
    daily_values: Iterable[float],
    hourly_times: Iterable[object],
    *,
    availability_lag_hours: int = 24,
    max_age_hours: int = 48,
    source_timezone: str = "UTC",
) -> np.ndarray:
    """Forward-fill only values known at each target time.

    Date-labelled daily aggregates are unavailable until the next day by
    default. Set ``availability_lag_hours=0`` only when the source timestamp is
    documented as an observation availability time rather than a day label.
    """

    source_time = normalise_times_to_utc(
        daily_times, source_timezone=source_timezone
    ) + pd.to_timedelta(availability_lag_hours, unit="h")
    target_time = normalise_times_to_utc(hourly_times, source_timezone=source_timezone)
    values = np.asarray(list(daily_values), dtype=float)
    if len(source_time) != len(values):
        raise ValueError("daily_times and daily_values lengths differ")
    if not source_time.is_monotonic_increasing or source_time.has_duplicates:
        raise ValueError("daily_times must be strictly increasing")
    positions = source_time.searchsorted(target_time, side="right") - 1
    output = np.full(len(target_time), np.nan, dtype=float)
    valid = positions >= 0
    if valid.any():
        ages = (target_time[valid] - source_time[positions[valid]]).total_seconds() / 3600.0
        fresh = ages <= max_age_hours
        valid_indices = np.flatnonzero(valid)[fresh]
        output[valid_indices] = values[positions[valid_indices]]
    return output


def align_daily_dataarray(
    daily: object,
    hourly_time: object,
    *,
    availability_lag_hours: int = 24,
    max_age_hours: int = 48,
) -> object:
    """Dask-compatible Xarray adapter using backward-only reindexing."""

    import xarray as xr

    if "time" not in daily.dims:
        raise ValueError("daily DataArray must have a time dimension")
    shifted = daily.assign_coords(
        time=daily.time + np.timedelta64(availability_lag_hours, "h")
    )
    target = xr.DataArray(hourly_time, dims="time", name="time")
    return shifted.reindex(time=target, method="ffill", tolerance=f"{max_age_hours}h")
