from __future__ import annotations

from burnwindows.optimizer import (
    explain_selection,
    greedy_schedule,
    solve_schedule,
    validate_selection,
)
from burnwindows.tools import optimize_burn_schedule


def test_validator_rejects_overlapping_demand(schedule_candidates) -> None:
    feasible, errors = validate_selection(schedule_candidates, ["a", "b"], crew_capacity=1)
    assert not feasible
    assert "crew capacity exceeded" in errors[0]


def test_optimizer_selects_best_non_overlapping_set(schedule_candidates) -> None:
    result = solve_schedule(schedule_candidates, crew_capacity=1)
    assert result.feasible
    assert set(result.selected_ids) == {"b", "c"}
    assert result.objective_value == 28
    explanations = explain_selection(schedule_candidates, result, crew_capacity=1)
    assert explanations["a"]["reason_code"] == "crew_capacity_conflict"
    assert explanations["a"]["blocking_selected_ids"] == ["b"]
    assert explanations["a"]["local_replacement_gap"] == 10


def test_minimum_duration_is_enforced(schedule_candidates) -> None:
    result = solve_schedule(schedule_candidates, crew_capacity=1, min_duration_hours=3.5)
    assert "c" not in result.selected_ids
    assert result.rejected["c"] == "shorter than minimum duration"


def test_greedy_is_feasible(schedule_candidates) -> None:
    result = greedy_schedule(schedule_candidates, crew_capacity=1, method="earliest-feasible")
    feasible, _ = validate_selection(schedule_candidates, result.selected_ids, crew_capacity=1)
    assert feasible


def test_tool_compares_milp_and_greedy(schedule_candidates) -> None:
    response = optimize_burn_schedule(candidates=schedule_candidates, crew_capacity=1)
    assert response.status == "ok"
    assert response.result["optimum"]["feasible"]
    assert response.result["lift_over_best_greedy"] >= 0
    frontier = response.result["crew_capacity_counterfactuals"]
    assert [row["crew_capacity"] for row in frontier] == [1, 2]
    assert frontier[1]["objective_value"] >= frontier[0]["objective_value"]
    assert response.result["selection_explanations"]["a"]["reason_code"] == "crew_capacity_conflict"

