"""Vectorised deterministic rule evaluation and continuous-window extraction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd

from .alignment import normalise_times_to_utc
from .models import BurnWindow, Condition, MissingPolicy, Prescription

SEASON_MONTHS = {
    "summer": {12, 1, 2},
    "autumn": {3, 4, 5},
    "winter": {6, 7, 8},
    "spring": {9, 10, 11},
}


def evaluate_condition(values: np.ndarray, condition: Condition) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    valid = np.isfinite(array)
    result = valid.copy()
    if condition.lower is not None:
        comparator = np.greater_equal if condition.lower.inclusive else np.greater
        result &= comparator(array, condition.lower.value)
    if condition.upper is not None:
        comparator = np.less_equal if condition.upper.inclusive else np.less
        result &= comparator(array, condition.upper.value)
    return result


def evaluate_prescription(
    data: Mapping[str, np.ndarray],
    prescription: Prescription,
    *,
    times: Sequence[object] | None = None,
    missing_policy: MissingPolicy = MissingPolicy.ERROR,
    include_unmapped: bool = False,
) -> tuple[np.ndarray, dict[str, np.ndarray], list[str]]:
    """Evaluate an AND-rule and return suitability, leaf masks and warnings."""

    shape = next((np.asarray(value).shape for value in data.values()), None)
    if shape is None:
        raise ValueError("data is empty")
    combined = np.ones(shape, dtype=bool)
    masks: dict[str, np.ndarray] = {}
    warnings: list[str] = []
    months = pd.DatetimeIndex(times).month if times is not None else None
    for index, condition in enumerate(prescription.conditions):
        key = f"{condition.field}:{index}"
        if condition.operational_status == "unmapped" and not include_unmapped:
            warnings.append(f"excluded unmapped constraint: {condition.field}")
            continue
        if condition.variable not in data:
            message = f"missing variable {condition.variable} for {condition.field}"
            if missing_policy == MissingPolicy.ERROR:
                raise KeyError(message)
            warnings.append(message)
            mask = np.zeros(shape, dtype=bool) if missing_policy == MissingPolicy.FAIL else np.ones(shape, dtype=bool)
        else:
            mask = evaluate_condition(np.asarray(data[condition.variable]), condition)
        if condition.season:
            if months is None:
                raise ValueError("times required for seasonal conditions")
            if shape[0] != len(months):
                raise ValueError("time axis length does not match data")
            active = np.isin(months, list(SEASON_MONTHS[condition.season]))
            active = active.reshape((len(active),) + (1,) * (len(shape) - 1))
            # A seasonal branch is neutral outside its active season.
            mask = np.where(active, mask, True)
        masks[key] = mask
        combined &= mask
    return combined, masks, warnings


def extract_windows(
    suitable: Sequence[bool],
    times: Sequence[object],
    *,
    min_duration_hours: int,
    location: str = "region",
    source_timezone: str = "UTC",
) -> list[BurnWindow]:
    """Extract consecutive hourly runs; irregular time gaps split windows."""

    if min_duration_hours < 1:
        raise ValueError("min_duration_hours must be positive")
    mask = np.asarray(suitable, dtype=bool)
    index = normalise_times_to_utc(times, source_timezone=source_timezone)
    if mask.ndim != 1 or len(mask) != len(index):
        raise ValueError("suitable and times must be equal-length 1D arrays")
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("times must be strictly increasing")
    windows: list[BurnWindow] = []
    start: int | None = None
    for position in range(len(mask) + 1):
        continues = position < len(mask) and mask[position]
        if continues and position and start is not None:
            continues = index[position] - index[position - 1] == pd.Timedelta(hours=1)
        if continues and start is None:
            start = position
        elif not continues and start is not None:
            duration = position - start
            if duration >= min_duration_hours:
                windows.append(
                    BurnWindow(
                        location=location,
                        start=index[start].to_pydatetime(),
                        end=(index[position - 1] + pd.Timedelta(hours=1)).to_pydatetime(),
                        duration_hours=duration,
                    )
                )
            start = position if position < len(mask) and mask[position] else None
    return windows


def limiting_factors(masks: Mapping[str, np.ndarray]) -> list[dict[str, float | int | str]]:
    if not masks:
        return []
    keys = list(masks)
    stacked = np.stack([np.asarray(masks[key], dtype=bool) for key in keys])
    fail = ~stacked
    total = int(fail[0].size)
    results = []
    for position, key in enumerate(keys):
        failures = int(fail[position].sum())
        exclusive = int((fail[position] & (fail.sum(axis=0) == 1)).sum())
        results.append(
            {
                "constraint": key,
                "failure_count": failures,
                "failure_rate": failures / total if total else 0.0,
                "exclusive_failure_count": exclusive,
            }
        )
    return sorted(results, key=lambda item: (-float(item["failure_rate"]), str(item["constraint"])))


def apply_threshold_override(condition: Condition, delta: float) -> Condition:
    """Widen (+) or narrow (-) both sides of a condition deterministically."""

    update = condition.model_copy(deep=True)
    if update.lower:
        update.lower.value -= delta
    if update.upper:
        update.upper.value += delta
    if update.lower and update.upper and update.lower.value > update.upper.value:
        raise ValueError("delta produces an inverted range")
    return update
