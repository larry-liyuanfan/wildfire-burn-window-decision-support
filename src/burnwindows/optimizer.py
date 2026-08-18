"""Greedy baselines and a binary linear scheduling formulation."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from itertools import combinations

import numpy as np

from .models import ScheduleCandidate, ScheduleResult


def _active(candidate: ScheduleCandidate, point: datetime) -> bool:
    return candidate.start <= point < candidate.end


def validate_selection(
    candidates: Iterable[ScheduleCandidate],
    selected_ids: Iterable[str],
    *,
    crew_capacity: int,
    daily_capacity: int | None = None,
) -> tuple[bool, list[str]]:
    candidates = list(candidates)
    selected_set = set(selected_ids)
    selected = [item for item in candidates if item.id in selected_set]
    errors: list[str] = []
    if len(selected) != len(selected_set):
        errors.append("selected ids contain unknown or duplicate candidates")
    points = sorted({item.start for item in selected} | {item.end for item in selected})
    for point in points:
        demand = sum(item.crew_demand for item in selected if _active(item, point))
        if demand > crew_capacity:
            errors.append(f"crew capacity exceeded at {point.isoformat()}: {demand}>{crew_capacity}")
    if daily_capacity is not None:
        per_day: dict[object, int] = defaultdict(int)
        for item in selected:
            per_day[item.start.date()] += 1
        for day, count in per_day.items():
            if count > daily_capacity:
                errors.append(f"daily capacity exceeded on {day}: {count}>{daily_capacity}")
    return not errors, errors


def greedy_schedule(
    candidates: Iterable[ScheduleCandidate],
    *,
    crew_capacity: int,
    min_duration_hours: float = 1.0,
    daily_capacity: int | None = None,
    method: str = "highest-score",
) -> ScheduleResult:
    pool = [item for item in candidates if item.duration_hours >= min_duration_hours]
    if method == "earliest-feasible":
        pool.sort(key=lambda item: (item.start, -item.objective_value, item.id))
    elif method == "highest-score":
        pool.sort(key=lambda item: (-item.objective_value, item.start, item.id))
    else:
        raise ValueError(f"unknown greedy method: {method}")
    selected: list[ScheduleCandidate] = []
    rejected: dict[str, str] = {}
    for item in pool:
        feasible, errors = validate_selection(
            [*selected, item],
            [candidate.id for candidate in [*selected, item]],
            crew_capacity=crew_capacity,
            daily_capacity=daily_capacity,
        )
        if feasible:
            selected.append(item)
        else:
            rejected[item.id] = "; ".join(errors)
    return ScheduleResult(
        method=method,
        selected_ids=[item.id for item in selected],
        objective_value=sum(item.objective_value for item in selected),
        feasible=True,
        rejected=rejected,
        solver_status="greedy-complete",
    )


def _constraint_rows(
    candidates: list[ScheduleCandidate], crew_capacity: int, daily_capacity: int | None
) -> tuple[list[list[float]], list[float]]:
    rows: list[list[float]] = []
    limits: list[float] = []
    points = sorted({item.start for item in candidates} | {item.end for item in candidates})
    for point in points:
        row = [float(item.crew_demand if _active(item, point) else 0) for item in candidates]
        if any(row):
            rows.append(row)
            limits.append(float(crew_capacity))
    if daily_capacity is not None:
        days = sorted({item.start.date() for item in candidates})
        for day in days:
            rows.append([float(item.start.date() == day) for item in candidates])
            limits.append(float(daily_capacity))
    return rows, limits


def solve_schedule(
    candidates: Iterable[ScheduleCandidate],
    *,
    crew_capacity: int,
    min_duration_hours: float = 1.0,
    daily_capacity: int | None = None,
) -> ScheduleResult:
    """Solve the binary linear programme, with exact enumeration as fallback."""

    if crew_capacity < 1:
        raise ValueError("crew_capacity must be positive")
    candidates = list(candidates)
    short = {item.id: "shorter than minimum duration" for item in candidates if item.duration_hours < min_duration_hours}
    pool = [item for item in candidates if item.id not in short]
    if not pool:
        return ScheduleResult(
            method="exact-fallback",
            selected_ids=[],
            objective_value=0.0,
            feasible=True,
            rejected=short,
            solver_status="empty-feasible-set",
        )
    rows, limits = _constraint_rows(pool, crew_capacity, daily_capacity)
    objective = np.asarray([-item.objective_value for item in pool], dtype=float)
    selected: list[str]
    method = "milp"
    status = ""
    try:
        from scipy.optimize import Bounds, LinearConstraint, milp

        constraints = None
        if rows:
            matrix = np.asarray(rows, dtype=float)
            constraints = LinearConstraint(matrix, -np.inf, np.asarray(limits, dtype=float))
        result = milp(
            c=objective,
            integrality=np.ones(len(pool)),
            bounds=Bounds(np.zeros(len(pool)), np.ones(len(pool))),
            constraints=constraints,
            options={"time_limit": 60.0},
        )
        if result.x is None:
            raise RuntimeError(result.message)
        selected = [item.id for item, value in zip(pool, result.x, strict=True) if value >= 0.5]
        status = f"scipy-status-{result.status}: {result.message}"
    except (ImportError, RuntimeError):
        if len(pool) > 24:
            raise RuntimeError("SciPy MILP unavailable and exact fallback is limited to 24 candidates")
        method = "exact-fallback"
        best_value = 0.0
        selected = []
        for count in range(1, len(pool) + 1):
            for subset in combinations(pool, count):
                ids = [item.id for item in subset]
                feasible, _ = validate_selection(
                    pool,
                    ids,
                    crew_capacity=crew_capacity,
                    daily_capacity=daily_capacity,
                )
                value = sum(item.objective_value for item in subset)
                if feasible and value > best_value + 1e-12:
                    best_value = value
                    selected = ids
        status = "enumerated-optimum"
    feasible, errors = validate_selection(
        pool,
        selected,
        crew_capacity=crew_capacity,
        daily_capacity=daily_capacity,
    )
    if not feasible:
        raise RuntimeError(f"solver returned infeasible selection: {errors}")
    rejected = dict(short)
    for item in pool:
        if item.id not in selected:
            rejected[item.id] = "not selected by objective/constraints"
    return ScheduleResult(
        method=method,
        selected_ids=selected,
        objective_value=sum(item.objective_value for item in pool if item.id in selected),
        feasible=True,
        rejected=rejected,
        solver_status=status,
        metadata={
            "formulation": "binary linear programme",
            "candidate_count": len(pool),
            "constraint_count": len(rows),
        },
    )

