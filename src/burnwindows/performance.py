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
    if min(
        statewide_cells,
        regional_cells,
        statewide_seconds,
        regional_seconds,
        statewide_rss,
        regional_rss,
    ) <= 0:
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
            "regional_vs_statewide_throughput_ratio": regional_throughput
            / statewide_throughput,
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
