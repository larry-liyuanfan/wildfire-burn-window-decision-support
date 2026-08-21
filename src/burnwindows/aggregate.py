"""Quality-gated aggregation for independently restartable VicClim6 years."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .trend import block_bootstrap_ci, theil_sen_slope


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def aggregate_vicclim6_years(
    run_root: str | Path,
    *,
    expected_years: Iterable[int],
) -> dict[str, Any]:
    """Aggregate annual result directories only after provenance checks pass."""

    root = Path(run_root)
    expected = tuple(sorted({int(year) for year in expected_years}))
    if not expected:
        raise ValueError("expected_years must not be empty")

    records: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for manifest_path in sorted(root.glob("*/run_manifest.json")):
        metrics_path = manifest_path.with_name("metrics.json")
        errors_path = manifest_path.with_name("error_cases.json")
        if not metrics_path.is_file() or not errors_path.is_file():
            raise ValueError(f"incomplete artifact bundle: {manifest_path.parent}")
        manifest = _read_json(manifest_path)
        metrics = _read_json(metrics_path)
        raw_year = manifest.get("runtime", {}).get("slurm_array_task_id")
        if raw_year is None:
            raw_year = str(metrics.get("time_coverage", {}).get("metric_start", ""))[:4]
        try:
            year = int(raw_year)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cannot determine year for {manifest_path.parent}") from exc
        if year in records:
            raise ValueError(f"duplicate annual result for {year}")
        records[year] = (manifest, metrics)

    missing = sorted(set(expected) - set(records))
    unexpected = sorted(set(records) - set(expected))
    if missing or unexpected:
        raise ValueError(f"year coverage mismatch: missing={missing}, unexpected={unexpected}")

    git_shas = {records[year][0].get("git_sha") for year in expected}
    burn_classes = {records[year][1].get("burn_class") for year in expected}
    scopes = {
        json.dumps(records[year][1].get("prescription_scope"), sort_keys=True) for year in expected
    }
    statuses = {records[year][1].get("evidence_status") for year in expected}
    region_scopes = {
        json.dumps(records[year][1].get("region_scope"), sort_keys=True) for year in expected
    }
    if len(git_shas) != 1 or "unknown" in git_shas:
        raise ValueError(f"annual runs do not share one known git SHA: {sorted(git_shas)}")
    if len(burn_classes) != 1 or len(scopes) != 1 or len(statuses) != 1 or len(region_scopes) != 1:
        raise ValueError("annual runs do not share one prescription/evidence/spatial contract")
    if any(records[year][0].get("data_kind") != "real" for year in expected):
        raise ValueError("all annual runs must use data_kind=real")

    evaluated = sum(int(records[year][1]["evaluated_space_time_cells"]) for year in expected)
    screened = sum(int(records[year][1]["suitable_space_time_cells"]) for year in expected)
    condition_names = set(records[expected[0]][1]["condition_failure_counts"])
    if any(
        set(records[year][1]["condition_failure_counts"]) != condition_names for year in expected
    ):
        raise ValueError("condition names changed across annual runs")
    condition_failures = {
        name: sum(int(records[year][1]["condition_failure_counts"][name]) for year in expected)
        for name in sorted(condition_names)
    }
    duration_names = set(records[expected[0]][1]["minimum_duration_endpoints"])
    if any(
        set(records[year][1]["minimum_duration_endpoints"]) != duration_names for year in expected
    ):
        raise ValueError("duration contract changed across annual runs")
    duration_endpoints = {
        duration: sum(
            int(records[year][1]["minimum_duration_endpoints"][duration]) for year in expected
        )
        for duration in sorted(duration_names, key=int)
    }

    sensitivity_payloads = [records[year][1].get("threshold_sensitivity") for year in expected]
    if any(payload is not None for payload in sensitivity_payloads) and not all(
        payload is not None for payload in sensitivity_payloads
    ):
        raise ValueError("threshold sensitivity is missing from some annual runs")
    threshold_sensitivity: dict[str, Any] | None = None
    if all(payload is not None for payload in sensitivity_payloads):
        payloads = [payload for payload in sensitivity_payloads if payload is not None]
        contracts = {
            json.dumps(
                {
                    "semantics": payload.get("semantics"),
                    "scenarios": [
                        {
                            "scenario": item.get("scenario"),
                            "overrides": item.get("overrides"),
                            "durations": sorted(
                                item.get("minimum_duration_endpoints", {}), key=int
                            ),
                        }
                        for item in payload.get("scenarios", [])
                    ],
                },
                sort_keys=True,
            )
            for payload in payloads
        }
        if len(contracts) != 1:
            raise ValueError("annual runs do not share one threshold-sensitivity contract")
        for year, payload in zip(expected, payloads, strict=True):
            metrics = records[year][1]
            baseline = payload.get("baseline", {})
            if int(baseline.get("provisional_pass_cells", -1)) != int(
                metrics["suitable_space_time_cells"]
            ):
                raise ValueError("threshold baseline does not match annual suitable cells")
            if baseline.get("minimum_duration_endpoints") != metrics.get(
                "minimum_duration_endpoints"
            ):
                raise ValueError("threshold baseline does not match annual duration endpoints")

        first_scenarios = payloads[0].get("scenarios", [])
        aggregate_scenarios: list[dict[str, Any]] = []
        baseline_rate = screened / evaluated if evaluated else 0.0
        for position, first in enumerate(first_scenarios):
            scenario_cells = sum(
                int(payload["scenarios"][position]["provisional_pass_cells"])
                for payload in payloads
            )
            scenario_rate = scenario_cells / evaluated if evaluated else 0.0
            aggregate_scenarios.append(
                {
                    "scenario": first["scenario"],
                    "overrides": first["overrides"],
                    "provisional_pass_cells": scenario_cells,
                    "provisional_pass_rate": scenario_rate,
                    "absolute_rate_change": scenario_rate - baseline_rate,
                    "relative_rate_change": (
                        (scenario_rate - baseline_rate) / baseline_rate if baseline_rate else None
                    ),
                    "minimum_duration_endpoints": {
                        duration: sum(
                            int(
                                payload["scenarios"][position]["minimum_duration_endpoints"][
                                    duration
                                ]
                            )
                            for payload in payloads
                        )
                        for duration in sorted(duration_names, key=int)
                    },
                    "warnings": sorted(
                        {
                            warning
                            for payload in payloads
                            for warning in payload["scenarios"][position].get("warnings", [])
                        }
                    ),
                }
            )
        threshold_sensitivity = {
            "semantics": payloads[0]["semantics"],
            "baseline": {
                "provisional_pass_cells": screened,
                "provisional_pass_rate": baseline_rate,
                "minimum_duration_endpoints": duration_endpoints,
            },
            "scenarios": aggregate_scenarios,
            "constraints": payloads[0].get("constraints", []),
        }

    annual = []
    for year in expected:
        metrics = records[year][1]
        annual.append(
            {
                "year": year,
                "evaluated_space_time_cells": int(metrics["evaluated_space_time_cells"]),
                "provisional_pass_cells": int(metrics["suitable_space_time_cells"]),
                "provisional_pass_rate": float(metrics["suitable_rate"]),
                "metric_hours": int(metrics["time_coverage"]["metric_hours"]),
                "left_censored": bool(metrics["time_coverage"]["left_censored"]),
            }
        )
    annual_rates = [float(item["provisional_pass_rate"]) for item in annual]
    slope = theil_sen_slope(expected, annual_rates)
    bootstrap_block_years = min(5, len(expected))
    trend_interval = block_bootstrap_ci(
        expected,
        annual_rates,
        block_size=bootstrap_block_years,
        samples=2000,
        seed=20260821,
    )

    result = {
        "evidence_status": next(iter(statuses)),
        "interpretation": "provisional mapped-condition screen; not operational burn windows",
        "git_sha": next(iter(git_shas)),
        "burn_class": next(iter(burn_classes)),
        "region_scope": records[expected[0]][1].get("region_scope"),
        "year_start": expected[0],
        "year_end": expected[-1],
        "year_count": len(expected),
        "evaluated_space_time_cells": evaluated,
        "provisional_pass_cells": screened,
        "provisional_pass_rate": screened / evaluated if evaluated else 0.0,
        "condition_failure_counts": condition_failures,
        "condition_failure_rates": {
            name: count / evaluated if evaluated else 0.0
            for name, count in condition_failures.items()
        },
        "minimum_duration_endpoints": duration_endpoints,
        "annual": annual,
        "descriptive_trend": {
            "estimator": "Theil-Sen slope with moving-block residual bootstrap",
            "slope_rate_per_year": slope,
            "change_rate_per_decade": slope * 10,
            "bootstrap_95pct_ci_rate_per_year": list(trend_interval),
            "bootstrap_block_years": bootstrap_block_years,
            "bootstrap_samples": 2000,
            "seed": 20260821,
            "causal_interpretation": False,
        },
        "quality_gate": {
            "complete_expected_year_set": True,
            "single_exact_git_sha": True,
            "single_prescription_contract": True,
            "single_spatial_contract": True,
            "single_threshold_sensitivity_contract": True,
            "all_real_data": True,
            "raw_paths_omitted": True,
        },
    }
    if threshold_sensitivity is not None:
        result["threshold_sensitivity"] = threshold_sensitivity
    return result
