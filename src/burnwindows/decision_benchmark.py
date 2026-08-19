"""Deterministic synthetic benchmark for scheduling decision value."""

from __future__ import annotations

import math
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from .models import ScheduleCandidate, ScheduleResult
from .optimizer import (
    greedy_schedule,
    solve_robust_schedule,
    solve_schedule,
    validate_selection,
)

REGIONS = ("east", "west", "north")


def generate_candidates(seed: int, days: int = 5) -> list[ScheduleCandidate]:
    rng = np.random.default_rng(seed)
    base = datetime(2026, 4, 1, 8, tzinfo=timezone.utc)
    candidates: list[ScheduleCandidate] = []
    for day in range(days):
        for slot, offset in enumerate((0, 1, 4, 5)):
            region = REGIONS[(day + slot) % len(REGIONS)]
            duration = int(rng.integers(3, 6))
            candidates.append(ScheduleCandidate(
                id=f"d{day}-s{slot}",
                region=region,
                start=base + timedelta(days=day, hours=offset),
                end=base + timedelta(days=day, hours=offset + duration),
                area_hectares=float(rng.integers(8, 31)),
                robustness=float(rng.uniform(0.62, 0.96)),
                quality=float(rng.uniform(0.0, 4.0)),
                crew_demand=int(rng.integers(1, 3)),
                mobilisation_cost=float(rng.uniform(1.0, 6.0)),
            ))
    return candidates


def design_scenarios(candidates: list[ScheduleCandidate]) -> dict[str, dict[str, float]]:
    scenarios: dict[str, dict[str, float]] = {}
    multipliers = {
        "nominal": {region: 1.0 for region in REGIONS},
        **{
            f"{shocked}_adverse": {
                region: (0.3 if region == shocked else 0.92) for region in REGIONS
            }
            for shocked in REGIONS
        },
    }
    for name, region_multipliers in multipliers.items():
        scenarios[name] = {
            item.id: (
                item.area_hectares * item.robustness * region_multipliers[item.region]
                + item.quality
                - item.mobilisation_cost
            )
            for item in candidates
        }
    return scenarios


def _realised_utility(
    candidates: list[ScheduleCandidate], selected_ids: list[str], multipliers: dict[str, float]
) -> float:
    selected = set(selected_ids)
    return sum(
        item.area_hectares * item.robustness * multipliers[item.region]
        + item.quality
        - item.mobilisation_cost
        for item in candidates
        if item.id in selected
    )


def _policy_metrics(
    candidates: list[ScheduleCandidate],
    result: ScheduleResult,
    held_out_multipliers: list[dict[str, float]],
    *,
    crew_capacity: int,
    daily_capacity: int | None,
    solve_seconds: float,
) -> dict[str, Any]:
    selected = [item for item in candidates if item.id in set(result.selected_ids)]
    realised = [
        _realised_utility(candidates, result.selected_ids, multipliers)
        for multipliers in held_out_multipliers
    ]
    feasible, errors = validate_selection(
        candidates,
        result.selected_ids,
        crew_capacity=crew_capacity,
        daily_capacity=daily_capacity,
    )
    if not feasible:
        raise RuntimeError(f"benchmark policy is infeasible: {errors}")
    horizon_hours = max(
        (max(item.end for item in candidates) - min(item.start for item in candidates)).total_seconds() / 3600,
        1.0,
    )
    crew_hours = sum(item.crew_demand * item.duration_hours for item in selected)
    return {
        "method": result.method,
        "selected_operations": len(selected),
        "selected_area_hectares": sum(item.area_hectares for item in selected),
        "mobilisation_cost_units": sum(item.mobilisation_cost for item in selected),
        "crew_hours": crew_hours,
        "crew_utilisation_over_schedule_span": crew_hours / (crew_capacity * horizon_hours),
        "nominal_objective": sum(item.objective_value for item in selected),
        "held_out_mean_utility": statistics.fmean(realised),
        "held_out_p05_utility": float(np.percentile(np.asarray(realised), 5)),
        "held_out_min_utility": min(realised),
        "held_out_std_utility": statistics.pstdev(realised),
        "feasible": feasible,
        "solve_seconds": solve_seconds,
    }


def run_decision_benchmark(
    *, seed: int = 20260819, held_out_scenarios: int = 500, crew_capacity: int = 2,
    daily_capacity: int | None = 3,
) -> dict[str, Any]:
    if held_out_scenarios < 20:
        raise ValueError("held_out_scenarios must be at least 20")
    candidates = generate_candidates(seed)
    scenarios = design_scenarios(candidates)
    rng = np.random.default_rng(seed + 1)
    held_out = []
    for _ in range(held_out_scenarios):
        multipliers = {region: float(rng.uniform(0.55, 1.02)) for region in REGIONS}
        shocked = REGIONS[int(rng.integers(0, len(REGIONS)))]
        multipliers[shocked] = float(rng.uniform(0.2, 0.55))
        held_out.append(multipliers)

    policies: dict[str, ScheduleResult] = {}
    solve_times: dict[str, float] = {}
    for name, solve in (
        ("earliest_greedy", lambda: greedy_schedule(
            candidates, crew_capacity=crew_capacity, daily_capacity=daily_capacity,
            method="earliest-feasible",
        )),
        ("highest_score_greedy", lambda: greedy_schedule(
            candidates, crew_capacity=crew_capacity, daily_capacity=daily_capacity,
            method="highest-score",
        )),
        ("nominal_milp", lambda: solve_schedule(
            candidates, crew_capacity=crew_capacity, daily_capacity=daily_capacity,
        )),
        ("robust_milp", lambda: solve_robust_schedule(
            candidates, scenarios, crew_capacity=crew_capacity, daily_capacity=daily_capacity,
        )),
    ):
        started = time.perf_counter()
        policies[name] = solve()
        solve_times[name] = time.perf_counter() - started

    metrics = {
        name: _policy_metrics(
            candidates,
            result,
            held_out,
            crew_capacity=crew_capacity,
            daily_capacity=daily_capacity,
            solve_seconds=solve_times[name],
        )
        for name, result in policies.items()
    }
    best_greedy_nominal = max(
        metrics["earliest_greedy"]["nominal_objective"],
        metrics["highest_score_greedy"]["nominal_objective"],
    )
    robust_p05 = metrics["robust_milp"]["held_out_p05_utility"]
    nominal_p05 = metrics["nominal_milp"]["held_out_p05_utility"]
    return {
        "scope": "deterministic synthetic operations benchmark; utility and mobilisation cost are scenario units, not dollars",
        "seed": seed,
        "candidate_count": len(candidates),
        "design_scenario_count": len(scenarios),
        "held_out_scenario_count": held_out_scenarios,
        "crew_capacity": crew_capacity,
        "daily_capacity": daily_capacity,
        "policies": metrics,
        "comparisons": {
            "nominal_milp_lift_over_best_greedy": (
                metrics["nominal_milp"]["nominal_objective"] / best_greedy_nominal - 1
                if best_greedy_nominal else None
            ),
            "robust_p05_lift_over_nominal_milp": (
                robust_p05 / nominal_p05 - 1 if not math.isclose(nominal_p05, 0.0) else None
            ),
        },
        "selected_ids": {name: result.selected_ids for name, result in policies.items()},
    }


def _bootstrap_mean_ci(values: list[float], *, seed: int, samples: int = 2000) -> list[float]:
    if not values:
        return [0.0, 0.0]
    rng = np.random.default_rng(seed)
    array = np.asarray(values, dtype=float)
    means = np.asarray([
        rng.choice(array, size=len(array), replace=True).mean() for _ in range(samples)
    ])
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def run_decision_benchmark_suite(
    *,
    seed: int = 20260819,
    repetitions: int = 30,
    held_out_scenarios: int = 200,
    crew_capacity: int = 2,
    daily_capacity: int | None = 3,
) -> dict[str, Any]:
    if repetitions < 5:
        raise ValueError("repetitions must be at least 5")
    runs = [
        run_decision_benchmark(
            seed=seed + offset,
            held_out_scenarios=held_out_scenarios,
            crew_capacity=crew_capacity,
            daily_capacity=daily_capacity,
        )
        for offset in range(repetitions)
    ]
    comparisons: dict[str, Any] = {}
    for key in (
        "nominal_milp_lift_over_best_greedy",
        "robust_p05_lift_over_nominal_milp",
    ):
        values = [float(run["comparisons"][key]) for run in runs if run["comparisons"][key] is not None]
        comparisons[key] = {
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "bootstrap_mean_95pct_ci": _bootstrap_mean_ci(values, seed=seed + 1000),
            "positive_run_rate": sum(value > 0 for value in values) / len(values),
        }
    policy_summary: dict[str, Any] = {}
    for name in runs[0]["policies"]:
        policy_rows = [run["policies"][name] for run in runs]
        policy_summary[name] = {
            "feasible_run_rate": sum(bool(row["feasible"]) for row in policy_rows) / len(policy_rows),
            "mean_nominal_objective": statistics.fmean(row["nominal_objective"] for row in policy_rows),
            "mean_held_out_p05_utility": statistics.fmean(row["held_out_p05_utility"] for row in policy_rows),
            "mean_selected_area_hectares": statistics.fmean(row["selected_area_hectares"] for row in policy_rows),
            "mean_mobilisation_cost_units": statistics.fmean(row["mobilisation_cost_units"] for row in policy_rows),
            "mean_crew_utilisation_over_schedule_span": statistics.fmean(
                row["crew_utilisation_over_schedule_span"] for row in policy_rows
            ),
            "median_solve_seconds": statistics.median(row["solve_seconds"] for row in policy_rows),
        }
    robust_cost = policy_summary["robust_milp"]["mean_mobilisation_cost_units"]
    nominal_cost = policy_summary["nominal_milp"]["mean_mobilisation_cost_units"]
    return {
        "scope": "multi-seed deterministic synthetic operations benchmark; utility and mobilisation cost are scenario units, not dollars",
        "seed_start": seed,
        "repetitions": repetitions,
        "held_out_scenarios_per_run": held_out_scenarios,
        "total_held_out_scenario_evaluations_per_policy": repetitions * held_out_scenarios,
        "candidate_count_per_run": runs[0]["candidate_count"],
        "design_scenario_count_per_run": runs[0]["design_scenario_count"],
        "crew_capacity": crew_capacity,
        "daily_capacity": daily_capacity,
        "comparisons": comparisons,
        "policies": policy_summary,
        "operational_proxy": {
            "robust_mean_mobilisation_cost_change_vs_nominal": (
                robust_cost / nominal_cost - 1 if nominal_cost else None
            ),
            "definition": "candidate mobilisation penalty in scenario utility units; not currency",
        },
        "per_run": [
            {
                "seed": run["seed"],
                "comparisons": run["comparisons"],
                "policies": run["policies"],
            }
            for run in runs
        ],
    }
