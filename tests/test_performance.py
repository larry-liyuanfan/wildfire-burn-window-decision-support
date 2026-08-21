from __future__ import annotations

from copy import deepcopy

import pytest

from burnwindows.performance import (
    compare_real_worker_scaling,
    compare_spatial_scope_performance,
)


def _record(*, cells: int, seconds: int, rss: int, regional: bool) -> dict:
    return {
        "jobs": {
            "array_task_count": 51,
            "array_elapsed_total_seconds": seconds,
            "array_max_rss_kib": rss,
        },
        "code_and_inputs": {"git_sha": "regional" if regional else "statewide"},
        "prescription_contract": {
            "burn_class": "fixture",
            "evaluated_mapped_conditions": 6,
            "unmapped_conditions": ["fuel", "ground wind"],
        },
        "result": {
            "year_start": 1973,
            "year_end": 2023,
            "year_count": 51,
            "evaluated_space_time_cells": cells,
        },
        "quality_gate": {
            "complete_expected_year_set": True,
            "all_real_data": True,
            "raw_paths_omitted": True,
        },
    }


def test_spatial_comparison_reports_observed_reductions_without_speedup_claim() -> None:
    result = compare_spatial_scope_performance(
        _record(cells=1000, seconds=100, rss=1000, regional=False),
        _record(cells=100, seconds=25, rss=200, regional=True),
    )

    assert result["derived"]["regional_cell_fraction"] == pytest.approx(0.1)
    assert result["derived"]["observed_elapsed_reduction"] == pytest.approx(0.75)
    assert result["derived"]["observed_max_rss_reduction"] == pytest.approx(0.8)
    assert result["derived"]["regional_vs_statewide_throughput_ratio"] == pytest.approx(0.4)
    assert "not a 1-to-4 worker scaling benchmark" in result["boundaries"][0]


def test_spatial_comparison_rejects_mixed_contract_or_failed_gate() -> None:
    statewide = _record(cells=1000, seconds=100, rss=1000, regional=False)
    regional = _record(cells=100, seconds=25, rss=200, regional=True)
    mixed = deepcopy(regional)
    mixed["result"]["year_end"] = 2022
    with pytest.raises(ValueError, match="comparison contract"):
        compare_spatial_scope_performance(statewide, mixed)

    failed = deepcopy(regional)
    failed["quality_gate"]["all_real_data"] = False
    with pytest.raises(ValueError, match="quality gate"):
        compare_spatial_scope_performance(statewide, failed)


def _scaling_record(*, workers: int, seconds: float) -> dict:
    return {
        "git_sha": "a" * 40,
        "evidence_status": "verified-real-partial-prescription-by-this-run",
        "data_kind": "real",
        "burn_class": "fixture",
        "prescription_scope": {"complete": False},
        "region_scope": {
            "label": "fixture district",
            "selected_grid_cells": 10,
            "source_path": "/restricted/boundary.geojson",
        },
        "time_coverage": {"dask_workers": workers},
        "suitable_space_time_cells": 10,
        "evaluated_space_time_cells": 100,
        "condition_failure_counts": {"temperature": 20},
        "minimum_duration_endpoints": {"2": 5},
        "threshold_sensitivity": {"scenarios": []},
        "wall_seconds": seconds,
    }


def test_real_worker_scaling_requires_equal_semantics() -> None:
    result = compare_real_worker_scaling(
        {
            1: _scaling_record(workers=1, seconds=40),
            2: _scaling_record(workers=2, seconds=24),
            4: _scaling_record(workers=4, seconds=16),
        }
    )
    assert result["derived"]["one_to_four_speedup"] == pytest.approx(2.5)
    assert result["derived"]["one_to_four_parallel_efficiency"] == pytest.approx(0.625)
    assert result["quality_gate"]["single_exact_git_sha"] is True
    assert "source_path" not in result["comparison_contract"]["region_scope"]

    changed = _scaling_record(workers=4, seconds=16)
    changed["suitable_space_time_cells"] = 9
    with pytest.raises(ValueError, match="semantic result"):
        compare_real_worker_scaling(
            {
                1: _scaling_record(workers=1, seconds=40),
                2: _scaling_record(workers=2, seconds=24),
                4: changed,
            }
        )

    unknown_sha = {
        workers: {**_scaling_record(workers=workers, seconds=seconds), "git_sha": "unknown"}
        for workers, seconds in ((1, 40), (2, 24), (4, 16))
    }
    with pytest.raises(ValueError, match="known run git SHA"):
        compare_real_worker_scaling(unknown_sha)
