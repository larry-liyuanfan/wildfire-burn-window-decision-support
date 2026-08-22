"""Strict comparisons between completed real-data performance records."""

from __future__ import annotations

from typing import Any


def _require(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"missing required field: {'.'.join(path)}")
        value = value[key]
    return value


def compare_spatial_scope_performance(
    statewide: dict[str, Any],
    regional: dict[str, Any],
) -> dict[str, Any]:
    """Compare observed resource use after an official spatial restriction.

    This deliberately does not call the result worker scaling or algorithmic
    speedup. The two completed chains have different spatial contracts and code
    SHAs, while sharing the same years and partial prescription contract.
    """

    for label, payload in (("statewide", statewide), ("regional", regional)):
        gate = _require(payload, ("quality_gate",))
        required_flags = ("complete_expected_year_set", "all_real_data", "raw_paths_omitted")
        if not all(gate.get(flag) is True for flag in required_flags):
            raise ValueError(f"{label} record did not pass the required real-data quality gate")
        if _require(payload, ("jobs", "array_task_count")) <= 0:
            raise ValueError(f"{label} record has no completed array tasks")

    shared_paths = (
        ("result", "year_start"),
        ("result", "year_end"),
        ("result", "year_count"),
        ("prescription_contract", "burn_class"),
        ("prescription_contract", "evaluated_mapped_conditions"),
        ("prescription_contract", "unmapped_conditions"),
    )
    for path in shared_paths:
        if _require(statewide, path) != _require(regional, path):
            raise ValueError(f"records do not share one comparison contract: {'.'.join(path)}")
    if _require(statewide, ("jobs", "array_task_count")) != _require(
        regional, ("jobs", "array_task_count")
    ):
        raise ValueError("records have different annual task counts")

    statewide_cells = int(_require(statewide, ("result", "evaluated_space_time_cells")))
    regional_cells = int(_require(regional, ("result", "evaluated_space_time_cells")))
    statewide_seconds = float(_require(statewide, ("jobs", "array_elapsed_total_seconds")))
    regional_seconds = float(_require(regional, ("jobs", "array_elapsed_total_seconds")))
    statewide_rss = int(_require(statewide, ("jobs", "array_max_rss_kib")))
    regional_rss = int(_require(regional, ("jobs", "array_max_rss_kib")))
    if (
        min(
            statewide_cells,
            regional_cells,
            statewide_seconds,
            regional_seconds,
            statewide_rss,
            regional_rss,
        )
        <= 0
    ):
        raise ValueError("performance inputs must be positive")

    cell_fraction = regional_cells / statewide_cells
    elapsed_fraction = regional_seconds / statewide_seconds
    rss_fraction = regional_rss / statewide_rss
    statewide_throughput = statewide_cells / statewide_seconds
    regional_throughput = regional_cells / regional_seconds

    return {
        "comparison_contract": {
            "year_start": _require(statewide, ("result", "year_start")),
            "year_end": _require(statewide, ("result", "year_end")),
            "year_count": _require(statewide, ("result", "year_count")),
            "annual_tasks_each": _require(statewide, ("jobs", "array_task_count")),
            "burn_class": _require(statewide, ("prescription_contract", "burn_class")),
            "evaluated_mapped_conditions": _require(
                statewide, ("prescription_contract", "evaluated_mapped_conditions")
            ),
            "unmapped_conditions": _require(
                statewide, ("prescription_contract", "unmapped_conditions")
            ),
        },
        "observed": {
            "statewide": {
                "evaluated_space_time_cells": statewide_cells,
                "array_elapsed_total_seconds": statewide_seconds,
                "array_max_rss_kib": statewide_rss,
                "throughput_cells_per_second": statewide_throughput,
                "git_sha": _require(statewide, ("code_and_inputs", "git_sha")),
            },
            "regional": {
                "evaluated_space_time_cells": regional_cells,
                "array_elapsed_total_seconds": regional_seconds,
                "array_max_rss_kib": regional_rss,
                "throughput_cells_per_second": regional_throughput,
                "git_sha": _require(regional, ("code_and_inputs", "git_sha")),
            },
        },
        "derived": {
            "regional_cell_fraction": cell_fraction,
            "regional_elapsed_fraction": elapsed_fraction,
            "regional_max_rss_fraction": rss_fraction,
            "observed_elapsed_reduction": 1.0 - elapsed_fraction,
            "observed_max_rss_reduction": 1.0 - rss_fraction,
            "regional_vs_statewide_throughput_ratio": regional_throughput / statewide_throughput,
            "elapsed_fraction_divided_by_cell_fraction": elapsed_fraction / cell_fraction,
        },
        "quality_gate": {
            "same_year_range": True,
            "same_annual_task_count": True,
            "same_partial_prescription_contract": True,
            "both_real_data_quality_gates_passed": True,
            "different_spatial_contracts_disclosed": True,
            "different_git_shas_disclosed": True,
        },
        "boundaries": [
            "This is an observed comparison between completed statewide and official-district chains, not a 1-to-4 worker scaling benchmark.",
            "The chains use different spatial contracts and Git SHAs; the comparison cannot isolate a causal code-level speedup.",
            "Lower regional throughput per cell is consistent with fixed file-opening, alignment and aggregation overhead, but this record does not estimate an Amdahl serial fraction.",
            "No result is a burn approval, complete prescription, safe-hour, treated-area, fire-risk or economic-value claim.",
        ],
    }


def compare_real_worker_scaling(
    records: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Compare 1/2/4-thread Dask runs only after semantic equality checks."""

    required = {1, 2, 4}
    if set(records) != required:
        raise ValueError(f"worker scaling requires exactly {sorted(required)}")
    reference = records[1]
    comparable_fields = (
        "git_sha",
        "evidence_status",
        "data_kind",
        "burn_class",
        "prescription_scope",
        "region_scope",
        "suitable_space_time_cells",
        "evaluated_space_time_cells",
        "condition_failure_counts",
        "minimum_duration_endpoints",
        "threshold_sensitivity",
    )
    for workers, payload in sorted(records.items()):
        if payload.get("data_kind") != "real":
            raise ValueError(f"workers={workers} is not a real-data record")
        if payload.get("time_coverage", {}).get("dask_workers") != workers:
            raise ValueError(f"workers={workers} record has a mismatched worker count")
        for field in comparable_fields:
            if payload.get(field) != reference.get(field):
                raise ValueError(f"workers={workers} changed the semantic result field {field}")
        if float(payload.get("wall_seconds", 0.0)) <= 0:
            raise ValueError(f"workers={workers} has no positive wall time")
    if reference.get("git_sha") in {None, "", "unknown"}:
        raise ValueError("worker scaling requires one known run git SHA")

    raw_region_scope = reference.get("region_scope") or {}
    public_region_scope = {
        key: raw_region_scope.get(key)
        for key in (
            "geometry_type",
            "selected_grid_cells",
            "total_grid_cells",
            "coverage_fraction_of_source_grid",
            "feature_properties",
            "coordinate_reference_system",
            "boundary_inclusion_rule",
            "label",
        )
        if raw_region_scope.get(key) is not None
    }

    one_worker_seconds = float(reference["wall_seconds"])
    observations = []
    for workers, payload in sorted(records.items()):
        seconds = float(payload["wall_seconds"])
        speedup = one_worker_seconds / seconds
        observations.append(
            {
                "dask_thread_workers": workers,
                "wall_seconds": seconds,
                "speedup_vs_one": speedup,
                "parallel_efficiency": speedup / workers,
            }
        )
    four_worker = observations[-1]
    return {
        "comparison_contract": {
            "scheduler": "threads",
            "workers": [1, 2, 4],
            "data_kind": "real",
            "same_workload": True,
            "semantic_results_equal": True,
            "evaluated_space_time_cells": int(reference["evaluated_space_time_cells"]),
            "burn_class": reference["burn_class"],
            "run_git_sha": reference["git_sha"],
            "region_scope": public_region_scope,
        },
        "observed": observations,
        "derived": {
            "one_to_four_speedup": four_worker["speedup_vs_one"],
            "one_to_four_parallel_efficiency": four_worker["parallel_efficiency"],
        },
        "quality_gate": {
            "exact_worker_set": True,
            "all_real_data": True,
            "same_semantic_results": True,
            "single_exact_git_sha": True,
            "positive_wall_times": True,
        },
        "boundaries": [
            "This measures one process using Dask's threaded scheduler with 1, 2 and 4 thread workers; it is not multi-node distributed scaling.",
            "The result applies only to the pinned data, rule, region, time range and storage state of these runs.",
            "No timing result is burn approval, safety, treated-area, risk-reduction or economic evidence.",
        ],
    }
