"""Summaries for an explicitly incomplete public weather-condition screen."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd


def continuous_run_counts(mask: np.ndarray, durations: Sequence[int] = (2, 4, 6)) -> dict[str, int]:
    """Count maximal true runs meeting each duration across a time-first grid."""

    values = np.asarray(mask, dtype=bool)
    if values.ndim < 1:
        raise ValueError("mask must have a time axis")
    flat = values.reshape(values.shape[0], -1)
    counts = {str(int(duration)): 0 for duration in durations}
    if any(int(duration) < 1 for duration in durations):
        raise ValueError("durations must be positive")
    for column in flat.T:
        padded = np.concatenate(([False], column, [False]))
        changes = np.diff(padded.astype(np.int8))
        starts = np.flatnonzero(changes == 1)
        ends = np.flatnonzero(changes == -1)
        lengths = ends - starts
        for duration in durations:
            counts[str(int(duration))] += int(np.count_nonzero(lengths >= int(duration)))
    return counts


def summarize_weather_screen(
    suitable: np.ndarray,
    times: Sequence[Any],
    masks: Mapping[str, np.ndarray],
    *,
    durations: Sequence[int] = (2, 4, 6),
) -> dict[str, Any]:
    """Summarize cell-hours, monthly rates, runs and descriptive constraints."""

    values = np.asarray(suitable, dtype=bool)
    index = pd.DatetimeIndex(times)
    if values.ndim < 1 or values.shape[0] != len(index):
        raise ValueError("time axis and mask are misaligned")
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("times must be strictly increasing")
    total = int(values.size)
    monthly: dict[str, dict[str, float | int]] = {}
    periods = index.to_period("M")
    for period in periods.unique():
        selector = np.asarray(periods == period)
        subset = values[selector]
        monthly[str(period)] = {
            "screened_cell_hours": int(subset.sum()),
            "evaluated_cell_hours": int(subset.size),
            "screen_rate": float(subset.mean()) if subset.size else 0.0,
        }
    limiting = []
    for name, raw_mask in masks.items():
        condition_mask = np.asarray(raw_mask, dtype=bool)
        if condition_mask.shape != values.shape:
            raise ValueError(f"condition mask {name} does not align")
        failures = int((~condition_mask).sum())
        limiting.append(
            {
                "constraint": name,
                "failure_count": failures,
                "failure_rate": failures / total if total else 0.0,
            }
        )
    limiting.sort(key=lambda item: (-float(item["failure_rate"]), str(item["constraint"])))
    return {
        "screened_cell_hours": int(values.sum()),
        "evaluated_cell_hours": total,
        "screen_rate": float(values.mean()) if total else 0.0,
        "maximal_run_counts_at_least_hours": continuous_run_counts(values, durations),
        "monthly": monthly,
        "limiting_factors": limiting,
    }
