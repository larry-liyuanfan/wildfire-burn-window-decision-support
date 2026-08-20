from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from burnwindows.models import ScheduleCandidate
from burnwindows.optimizer import solve_cvar_schedule, solve_robust_schedule


def test_robust_optimizer_maximises_worst_case_scenario() -> None:
    start = datetime(2026, 4, 1, 8, tzinfo=timezone.utc)
    candidates = [
        ScheduleCandidate(
            id="high-nominal",
            region="east",
            start=start,
            end=start + timedelta(hours=4),
            area_hectares=20,
        ),
        ScheduleCandidate(
            id="stable",
            region="west",
            start=start,
            end=start + timedelta(hours=4),
            area_hectares=12,
        ),
    ]
    result = solve_robust_schedule(
        candidates,
        {
            "nominal": {"high-nominal": 20.0, "stable": 12.0},
            "east-adverse": {"high-nominal": 3.0, "stable": 11.0},
        },
        crew_capacity=1,
    )
    assert result.selected_ids == ["stable"]
    assert result.objective_value == 11.0
    assert result.feasible
    assert result.metadata["solver_proof"]["optimality_proven"]
    assert result.metadata["feasibility_certificate"]["feasible"]


def test_robust_optimizer_rejects_incomplete_scenarios() -> None:
    start = datetime(2026, 4, 1, 8, tzinfo=timezone.utc)
    candidates = [ScheduleCandidate(
        id="a", region="east", start=start, end=start + timedelta(hours=3), area_hectares=5,
    )]
    try:
        solve_robust_schedule(candidates, {"scenario": {}}, crew_capacity=1)
    except ValueError as exc:
        assert "lacks candidate utilities" in str(exc)
    else:
        raise AssertionError("incomplete scenario should fail")


def test_cvar_optimizer_protects_lower_tail() -> None:
    start = datetime(2026, 4, 1, 8, tzinfo=timezone.utc)
    candidates = [
        ScheduleCandidate(
            id="volatile",
            region="east",
            start=start,
            end=start + timedelta(hours=4),
            area_hectares=20,
        ),
        ScheduleCandidate(
            id="stable",
            region="west",
            start=start,
            end=start + timedelta(hours=4),
            area_hectares=12,
        ),
    ]
    scenarios = {
        f"s{index}": {
            "volatile": value,
            "stable": 11.0,
        }
        for index, value in enumerate((20.0, 20.0, 20.0, 20.0, 2.0))
    }
    result = solve_cvar_schedule(candidates, scenarios, crew_capacity=1, alpha=0.8)
    assert result.selected_ids == ["stable"]
    assert result.objective_value == pytest.approx(11.0)
    assert result.metadata["tail_fraction"] == pytest.approx(0.2)
    assert result.metadata["solver_proof"]["optimality_proven"]
    assert result.metadata["feasibility_certificate"]["feasible"]


def test_cvar_optimizer_rejects_invalid_alpha() -> None:
    start = datetime(2026, 4, 1, 8, tzinfo=timezone.utc)
    candidate = ScheduleCandidate(
        id="a",
        region="east",
        start=start,
        end=start + timedelta(hours=3),
        area_hectares=5,
    )
    with pytest.raises(ValueError, match="alpha"):
        solve_cvar_schedule([candidate], {"s": {"a": 1.0}}, crew_capacity=1, alpha=1.0)
