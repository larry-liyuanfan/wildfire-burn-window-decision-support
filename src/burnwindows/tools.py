"""Deterministic, JSON-schema-compatible domain tools.

These functions contain no LLM calls. An agent may choose and parameterise a
tool, but the evidence calculation and constraint validation remain auditable.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np

from .engine import (
    apply_threshold_override,
    evaluate_prescription,
    extract_windows,
    limiting_factors,
)
from .models import (
    ExplainLimitingFactorsRequest,
    FindBurnWindowsRequest,
    MissingPolicy,
    OptimizeScheduleRequest,
    Prescription,
    RegionTrendRequest,
    ScheduleCandidate,
    ThresholdScenarioRequest,
    ToolEnvelope,
)
from .optimizer import explain_selection, greedy_schedule, solve_schedule
from .trend import block_bootstrap_ci, theil_sen_slope


def tool_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON Schemas suitable for a function-calling registry."""

    models = {
        "find_burn_windows": FindBurnWindowsRequest,
        "explain_limiting_factors": ExplainLimitingFactorsRequest,
        "compare_threshold_scenarios": ThresholdScenarioRequest,
        "get_region_trend": RegionTrendRequest,
        "optimize_burn_schedule": OptimizeScheduleRequest,
    }
    return {name: model.model_json_schema() for name, model in models.items()}


def find_burn_windows(
    *,
    times: Sequence[object],
    data: Mapping[str, Sequence[float]],
    prescription: Prescription | Mapping[str, Any],
    min_duration_hours: int = 2,
    location: str = "region",
    source_timezone: str = "UTC",
    missing_policy: MissingPolicy = MissingPolicy.ERROR,
    data_version: str = "unknown",
) -> ToolEnvelope:
    rule = prescription if isinstance(prescription, Prescription) else Prescription.model_validate(prescription)
    arrays = {key: np.asarray(value) for key, value in data.items()}
    suitable, _, warnings = evaluate_prescription(
        arrays, rule, times=times, missing_policy=missing_policy
    )
    if suitable.ndim != 1:
        raise ValueError("tool contract expects one regional time series")
    windows = extract_windows(
        suitable,
        times,
        min_duration_hours=min_duration_hours,
        location=location,
        source_timezone=source_timezone,
    )
    return ToolEnvelope(
        status="partial" if warnings or rule.unresolved else "ok",
        data_version=data_version,
        source=rule.source,
        constraints=[f"minimum continuous duration: {min_duration_hours}h"],
        warnings=[*warnings, *[f"unresolved {key}: {value}" for key, value in rule.unresolved.items()]],
        result={
            "windows": [item.model_dump(mode="json") for item in windows],
            "suitable_hours": int(suitable.sum()),
            "evaluated_hours": int(suitable.size),
            "suitable_rate": float(suitable.mean()) if suitable.size else 0.0,
        },
    )


def explain_limiting_factors(
    *,
    times: Sequence[object],
    data: Mapping[str, Sequence[float]],
    prescription: Prescription | Mapping[str, Any],
    missing_policy: MissingPolicy = MissingPolicy.ERROR,
    data_version: str = "unknown",
) -> ToolEnvelope:
    rule = prescription if isinstance(prescription, Prescription) else Prescription.model_validate(prescription)
    arrays = {key: np.asarray(value) for key, value in data.items()}
    _, masks, warnings = evaluate_prescription(
        arrays, rule, times=times, missing_policy=missing_policy
    )
    return ToolEnvelope(
        status="partial" if warnings else "ok",
        data_version=data_version,
        source=rule.source,
        warnings=warnings,
        constraints=["failure attribution is descriptive and does not imply causality"],
        result={"factors": limiting_factors(masks)},
    )


def compare_threshold_scenarios(
    *,
    times: Sequence[object],
    data: Mapping[str, Sequence[float]],
    prescription: Prescription | Mapping[str, Any],
    scenarios: Mapping[str, Mapping[str, float]],
    missing_policy: MissingPolicy = MissingPolicy.ERROR,
    data_version: str = "unknown",
) -> ToolEnvelope:
    """Compare field-specific widening deltas against an unchanged baseline."""

    rule = prescription if isinstance(prescription, Prescription) else Prescription.model_validate(prescription)
    arrays = {key: np.asarray(value) for key, value in data.items()}
    outcomes: list[dict[str, Any]] = []
    all_scenarios = {"baseline": {}, **dict(scenarios)}
    for name in sorted(all_scenarios):
        overrides = all_scenarios[name]
        scenario_rule = rule.model_copy(deep=True)
        scenario_rule.conditions = [
            apply_threshold_override(condition, float(overrides.get(condition.field, 0.0)))
            for condition in scenario_rule.conditions
        ]
        suitable, _, warnings = evaluate_prescription(
            arrays, scenario_rule, times=times, missing_policy=missing_policy
        )
        outcomes.append(
            {
                "scenario": name,
                "suitable_rate": float(suitable.mean()) if suitable.size else 0.0,
                "suitable_hours": int(suitable.sum()),
                "warnings": warnings,
            }
        )
    return ToolEnvelope(
        status="ok",
        data_version=data_version,
        source=rule.source,
        constraints=["positive deltas widen ranges; results are scenarios, not forecasts"],
        result={"scenarios": outcomes},
    )


def get_region_trend(
    *,
    years: Sequence[int],
    suitable_rates: Sequence[float],
    region: str,
    block_size: int = 3,
    bootstrap_samples: int = 500,
    data_version: str = "unknown",
) -> ToolEnvelope:
    slope = theil_sen_slope(years, suitable_rates)
    low, high = block_bootstrap_ci(
        years,
        suitable_rates,
        block_size=block_size,
        samples=bootstrap_samples,
    )
    return ToolEnvelope(
        status="ok",
        data_version=data_version,
        source="derived regional annual burn-window series",
        constraints=["descriptive Theil-Sen trend; no causal attribution"],
        result={
            "region": region,
            "slope_per_year": slope,
            "bootstrap_95pct_ci": [low, high],
            "observations": len(years),
        },
    )


def optimize_burn_schedule(
    *,
    candidates: Iterable[ScheduleCandidate | Mapping[str, Any]],
    crew_capacity: int,
    min_duration_hours: float = 2.0,
    daily_capacity: int | None = None,
    data_version: str = "unknown",
) -> ToolEnvelope:
    parsed = [
        item if isinstance(item, ScheduleCandidate) else ScheduleCandidate.model_validate(item)
        for item in candidates
    ]
    optimum = solve_schedule(
        parsed,
        crew_capacity=crew_capacity,
        min_duration_hours=min_duration_hours,
        daily_capacity=daily_capacity,
    )
    earliest = greedy_schedule(
        parsed,
        crew_capacity=crew_capacity,
        min_duration_hours=min_duration_hours,
        daily_capacity=daily_capacity,
        method="earliest-feasible",
    )
    highest = greedy_schedule(
        parsed,
        crew_capacity=crew_capacity,
        min_duration_hours=min_duration_hours,
        daily_capacity=daily_capacity,
        method="highest-score",
    )
    best_greedy = max(earliest.objective_value, highest.objective_value)
    lift = (optimum.objective_value - best_greedy) / best_greedy if best_greedy > 0 else 0.0
    capacity_levels = sorted({max(1, crew_capacity - 1), crew_capacity, crew_capacity + 1})
    capacity_frontier = []
    previous_objective: float | None = None
    for capacity in capacity_levels:
        counterfactual = solve_schedule(
            parsed,
            crew_capacity=capacity,
            min_duration_hours=min_duration_hours,
            daily_capacity=daily_capacity,
        )
        capacity_frontier.append(
            {
                "crew_capacity": capacity,
                "objective_value": counterfactual.objective_value,
                "selected_ids": counterfactual.selected_ids,
                "marginal_utility_vs_previous_level": (
                    None
                    if previous_objective is None
                    else counterfactual.objective_value - previous_objective
                ),
            }
        )
        previous_objective = counterfactual.objective_value
    return ToolEnvelope(
        status="ok",
        data_version=data_version,
        source="candidate windows supplied by caller",
        constraints=[
            f"crew capacity: {crew_capacity}",
            f"minimum duration: {min_duration_hours}h",
            "objective units are scenario utility, not realised financial return",
            "capacity frontier is a discrete counterfactual, not an LP shadow price",
            "rejection replacement gaps are local diagnostics, not causal values",
        ],
        result={
            "optimum": optimum.model_dump(mode="json"),
            "baselines": {
                "earliest_feasible": earliest.model_dump(mode="json"),
                "highest_score": highest.model_dump(mode="json"),
            },
            "lift_over_best_greedy": lift,
            "selection_explanations": explain_selection(
                parsed,
                optimum,
                crew_capacity=crew_capacity,
                daily_capacity=daily_capacity,
            ),
            "crew_capacity_counterfactuals": capacity_frontier,
        },
    )
