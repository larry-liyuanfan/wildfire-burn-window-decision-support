import json
from pathlib import Path

import pytest

from burnwindows.aggregate import aggregate_vicclim6_years


def _annual(
    root: Path,
    year: int,
    *,
    sha: str = "abc123",
    sensitivity: bool = False,
) -> None:
    target = root / f"vicclim6-year-99_{year}"
    target.mkdir(parents=True)
    (target / "run_manifest.json").write_text(
        json.dumps(
            {
                "git_sha": sha,
                "data_kind": "real",
                "runtime": {"slurm_array_task_id": str(year)},
            }
        ),
        encoding="utf-8",
    )
    metrics = {
        "evidence_status": "verified-real-partial-prescription-by-this-run",
        "burn_class": "fixture class",
        "prescription_scope": {
            "complete": False,
            "evaluated_condition_count": 2,
        },
        "region_scope": {
            "label": "fixture district",
            "selected_grid_cells": 5,
        },
        "time_coverage": {
            "metric_start": f"{year}-01-01T00:00:00",
            "metric_hours": 2,
            "left_censored": year == 1973,
        },
        "evaluated_space_time_cells": 10,
        "suitable_space_time_cells": year - 1972,
        "suitable_rate": (year - 1972) / 10,
        "condition_failure_counts": {"a": 2, "b": 3},
        "minimum_duration_endpoints": {"2": 1, "4": 0},
    }
    if sensitivity:
        scenario_cells = year - 1971
        metrics["threshold_sensitivity"] = {
            "semantics": "fixture absolute deltas",
            "baseline": {
                "provisional_pass_cells": year - 1972,
                "provisional_pass_rate": (year - 1972) / 10,
                "minimum_duration_endpoints": {"2": 1, "4": 0},
            },
            "scenarios": [
                {
                    "scenario": "wider",
                    "overrides": {"Temperature": 2.0},
                    "provisional_pass_cells": scenario_cells,
                    "provisional_pass_rate": scenario_cells / 10,
                    "minimum_duration_endpoints": {"2": 2, "4": 1},
                    "warnings": [],
                }
            ],
            "constraints": ["fixture only"],
        }
    (target / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (target / "error_cases.json").write_text("[]\n", encoding="utf-8")


def test_annual_aggregation_is_weighted_and_quality_gated(tmp_path: Path) -> None:
    _annual(tmp_path, 1973)
    _annual(tmp_path, 1974)

    result = aggregate_vicclim6_years(tmp_path, expected_years=[1973, 1974])

    assert result["evaluated_space_time_cells"] == 20
    assert result["provisional_pass_cells"] == 3
    assert result["provisional_pass_rate"] == 0.15
    assert result["condition_failure_counts"] == {"a": 4, "b": 6}
    assert result["minimum_duration_endpoints"] == {"2": 2, "4": 0}
    assert result["descriptive_trend"]["slope_rate_per_year"] == 0.1
    assert result["descriptive_trend"]["causal_interpretation"] is False
    assert result["quality_gate"]["complete_expected_year_set"] is True
    assert result["quality_gate"]["single_spatial_contract"] is True
    assert result["region_scope"]["selected_grid_cells"] == 5


def test_annual_aggregation_rejects_missing_or_mixed_sha(tmp_path: Path) -> None:
    _annual(tmp_path, 1973)
    with pytest.raises(ValueError, match="coverage mismatch"):
        aggregate_vicclim6_years(tmp_path, expected_years=[1973, 1974])

    _annual(tmp_path, 1974, sha="different")
    with pytest.raises(ValueError, match="one known git SHA"):
        aggregate_vicclim6_years(tmp_path, expected_years=[1973, 1974])


def test_annual_aggregation_combines_one_sensitivity_contract(tmp_path: Path) -> None:
    _annual(tmp_path, 1973, sensitivity=True)
    _annual(tmp_path, 1974, sensitivity=True)

    result = aggregate_vicclim6_years(tmp_path, expected_years=[1973, 1974])

    sensitivity = result["threshold_sensitivity"]
    assert sensitivity["baseline"]["provisional_pass_cells"] == 3
    assert sensitivity["scenarios"][0]["provisional_pass_cells"] == 5
    assert sensitivity["scenarios"][0]["provisional_pass_rate"] == 0.25
    assert sensitivity["scenarios"][0]["minimum_duration_endpoints"] == {
        "2": 4,
        "4": 2,
    }
    effects = sensitivity["scenarios"][0]["annual_effects"]
    assert [item["absolute_rate_change"] for item in effects] == pytest.approx([0.1, 0.1])
    effect_summary = sensitivity["scenarios"][0]["annual_effect_summary"]
    assert effect_summary["positive_year_count"] == 2
    assert effect_summary[
        "moving_block_bootstrap_95pct_ci_mean_absolute_rate_change"
    ] == pytest.approx([0.1, 0.1])
    assert result["quality_gate"]["single_threshold_sensitivity_contract"] is True
