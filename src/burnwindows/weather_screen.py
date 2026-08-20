"""Summaries for an explicitly incomplete public weather-condition screen."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(slots=True)
class StreamingWeatherScreenSummary:
    """Checkpointable summary that preserves true runs across time chunks."""

    durations: tuple[int, ...] = (2, 4, 6)
    grid_shape: tuple[int, ...] | None = None
    processed_hours: int = 0
    evaluated_cell_hours: int = 0
    screened_cell_hours: int = 0
    completed_run_counts: dict[str, int] = field(default_factory=dict)
    monthly: dict[str, dict[str, int]] = field(default_factory=dict)
    limiting_failures: dict[str, int] = field(default_factory=dict)
    current_runs: np.ndarray | None = None
    last_time: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        self.durations = tuple(int(duration) for duration in self.durations)
        if not self.durations or any(duration < 1 for duration in self.durations):
            raise ValueError("durations must be positive")
        if not self.completed_run_counts:
            self.completed_run_counts = {str(duration): 0 for duration in self.durations}

    def update(
        self,
        suitable: np.ndarray,
        times: Sequence[Any],
        masks: Mapping[str, np.ndarray],
    ) -> None:
        values = np.asarray(suitable, dtype=bool)
        index = pd.DatetimeIndex(times)
        if values.ndim < 1 or values.shape[0] != len(index) or not len(index):
            raise ValueError("time axis and mask are misaligned or empty")
        if not index.is_monotonic_increasing or index.has_duplicates:
            raise ValueError("times must be strictly increasing")
        if self.last_time is not None and index[0] != self.last_time + pd.Timedelta(hours=1):
            raise ValueError("chunks must form a continuous hourly time axis")
        shape = tuple(int(value) for value in values.shape[1:])
        if self.grid_shape is None:
            self.grid_shape = shape
            self.current_runs = np.zeros(int(np.prod(shape)), dtype=np.int32)
            self.limiting_failures = {str(name): 0 for name in masks}
        elif shape != self.grid_shape:
            raise ValueError("grid shape changed across chunks")
        if set(masks) != set(self.limiting_failures):
            raise ValueError("condition mask names changed across chunks")

        flat = values.reshape(values.shape[0], -1)
        assert self.current_runs is not None
        for row in flat:
            ended = self.current_runs[~row]
            for duration in self.durations:
                self.completed_run_counts[str(duration)] += int(
                    np.count_nonzero(ended >= duration)
                )
            self.current_runs = np.where(row, self.current_runs + 1, 0)

        periods = index.to_period("M")
        for period in periods.unique():
            selector = np.asarray(periods == period)
            subset = values[selector]
            target = self.monthly.setdefault(
                str(period), {"screened_cell_hours": 0, "evaluated_cell_hours": 0}
            )
            target["screened_cell_hours"] += int(subset.sum())
            target["evaluated_cell_hours"] += int(subset.size)
        for name, raw_mask in masks.items():
            condition_mask = np.asarray(raw_mask, dtype=bool)
            if condition_mask.shape != values.shape:
                raise ValueError(f"condition mask {name} does not align")
            self.limiting_failures[str(name)] += int((~condition_mask).sum())

        self.processed_hours += len(index)
        self.evaluated_cell_hours += int(values.size)
        self.screened_cell_hours += int(values.sum())
        self.last_time = index[-1]

    def summary(self) -> dict[str, Any]:
        current = self.current_runs
        run_counts = dict(self.completed_run_counts)
        if current is not None:
            for duration in self.durations:
                run_counts[str(duration)] += int(np.count_nonzero(current >= duration))
        monthly = {
            period: {
                **counts,
                "screen_rate": counts["screened_cell_hours"]
                / counts["evaluated_cell_hours"],
            }
            for period, counts in self.monthly.items()
        }
        limiting = [
            {
                "constraint": name,
                "failure_count": failures,
                "failure_rate": failures / self.evaluated_cell_hours
                if self.evaluated_cell_hours
                else 0.0,
            }
            for name, failures in self.limiting_failures.items()
        ]
        limiting.sort(key=lambda item: (-float(item["failure_rate"]), str(item["constraint"])))
        return {
            "screened_cell_hours": self.screened_cell_hours,
            "evaluated_cell_hours": self.evaluated_cell_hours,
            "screen_rate": self.screened_cell_hours / self.evaluated_cell_hours
            if self.evaluated_cell_hours
            else 0.0,
            "maximal_run_counts_at_least_hours": run_counts,
            "monthly": monthly,
            "limiting_factors": limiting,
        }

    def checkpoint(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "durations": list(self.durations),
            "grid_shape": list(self.grid_shape) if self.grid_shape is not None else None,
            "processed_hours": self.processed_hours,
            "evaluated_cell_hours": self.evaluated_cell_hours,
            "screened_cell_hours": self.screened_cell_hours,
            "completed_run_counts": self.completed_run_counts,
            "monthly": self.monthly,
            "limiting_failures": self.limiting_failures,
            "current_runs": self.current_runs.tolist() if self.current_runs is not None else None,
            "last_time": self.last_time.isoformat() if self.last_time is not None else None,
        }

    @classmethod
    def from_checkpoint(cls, payload: Mapping[str, Any]) -> StreamingWeatherScreenSummary:
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported weather-screen checkpoint schema")
        instance = cls(durations=tuple(int(value) for value in payload["durations"]))
        raw_shape = payload.get("grid_shape")
        instance.grid_shape = tuple(int(value) for value in raw_shape) if raw_shape else None
        instance.processed_hours = int(payload["processed_hours"])
        instance.evaluated_cell_hours = int(payload["evaluated_cell_hours"])
        instance.screened_cell_hours = int(payload["screened_cell_hours"])
        instance.completed_run_counts = {
            str(key): int(value) for key, value in payload["completed_run_counts"].items()
        }
        instance.monthly = {
            str(period): {str(key): int(value) for key, value in counts.items()}
            for period, counts in payload["monthly"].items()
        }
        instance.limiting_failures = {
            str(key): int(value) for key, value in payload["limiting_failures"].items()
        }
        raw_runs = payload.get("current_runs")
        instance.current_runs = (
            np.asarray(raw_runs, dtype=np.int32) if raw_runs is not None else None
        )
        raw_time = payload.get("last_time")
        instance.last_time = pd.Timestamp(raw_time) if raw_time else None
        return instance


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
