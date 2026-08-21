"""Robust deterministic trend summaries without claiming causality."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations

import numpy as np


def theil_sen_slope(years: Sequence[float], values: Sequence[float]) -> float:
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    if len(x) < 2:
        raise ValueError("at least two finite observations are required")
    slopes = [
        (y[j] - y[i]) / (x[j] - x[i]) for i, j in combinations(range(len(x)), 2) if x[j] != x[i]
    ]
    if not slopes:
        raise ValueError("years must contain at least two distinct values")
    return float(np.median(slopes))


def block_bootstrap_ci(
    years: Sequence[float],
    values: Sequence[float],
    *,
    block_size: int = 3,
    samples: int = 500,
    seed: int = 20260818,
) -> tuple[float, float]:
    x = np.asarray(years, dtype=float)
    y = np.asarray(values, dtype=float)
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("equal-length series with at least two observations required")
    if block_size < 1 or block_size > len(x):
        raise ValueError("invalid block_size")
    rng = np.random.default_rng(seed)
    residual = y - (np.median(y) + theil_sen_slope(x, y) * (x - np.median(x)))
    slopes: list[float] = []
    for _ in range(samples):
        draw: list[float] = []
        while len(draw) < len(y):
            start = int(rng.integers(0, len(y) - block_size + 1))
            draw.extend(residual[start : start + block_size])
        simulated = y - residual + np.asarray(draw[: len(y)])
        slopes.append(theil_sen_slope(x, simulated))
    return float(np.quantile(slopes, 0.025)), float(np.quantile(slopes, 0.975))


def moving_block_bootstrap_mean_ci(
    values: Sequence[float],
    *,
    block_size: int = 3,
    samples: int = 500,
    seed: int = 20260818,
) -> tuple[float, float]:
    """Estimate a mean interval while preserving bounded serial blocks."""

    array = np.asarray(values, dtype=float)
    if len(array) < 2 or not np.isfinite(array).all():
        raise ValueError("at least two finite values are required")
    if block_size < 1 or block_size > len(array):
        raise ValueError("invalid block_size")
    if samples < 20:
        raise ValueError("samples must be at least 20")
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(samples):
        draw: list[float] = []
        while len(draw) < len(array):
            start = int(rng.integers(0, len(array) - block_size + 1))
            draw.extend(array[start : start + block_size])
        means.append(float(np.mean(draw[: len(array)])))
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))
