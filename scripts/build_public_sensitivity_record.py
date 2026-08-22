"""Build a redacted public record from a completed 51-year sensitivity summary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from burnwindows.manifest import git_sha, write_json


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_public_record(summary: dict, *, summary_file: str, summary_sha256: str) -> dict:
    raw_region = summary.get("region_scope") or {}
    region = {
        key: raw_region.get(key)
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
        if raw_region.get(key) is not None
    }
    sensitivity = summary["threshold_sensitivity"]
    scenarios = []
    for scenario in sensitivity["scenarios"]:
        scenarios.append(
            {
                key: scenario.get(key)
                for key in (
                    "scenario",
                    "overrides",
                    "provisional_pass_cells",
                    "provisional_pass_rate",
                    "absolute_rate_change",
                    "relative_rate_change",
                    "minimum_duration_endpoints",
                    "annual_effect_summary",
                )
            }
        )
    return {
        "artifact_type": "vicclim6_murray_goldfields_51y_threshold_sensitivity",
        "evidence_status": summary["evidence_status"],
        "input_summary": {"file": summary_file, "sha256": summary_sha256},
        "annual_run_git_sha": summary["git_sha"],
        "aggregation_git_sha": summary.get("aggregation_git_sha"),
        "record_builder_git_sha": git_sha(),
        "scope": {
            "burn_class": summary["burn_class"],
            "region": region,
            "year_start": summary["year_start"],
            "year_end": summary["year_end"],
            "year_count": summary["year_count"],
            "evaluated_space_time_cells": summary["evaluated_space_time_cells"],
        },
        "baseline": {
            "provisional_pass_cells": summary["provisional_pass_cells"],
            "provisional_pass_rate": summary["provisional_pass_rate"],
            "minimum_duration_endpoints": summary["minimum_duration_endpoints"],
        },
        "threshold_sensitivity": {
            "semantics": sensitivity["semantics"],
            "scenarios": scenarios,
            "annual_effect_interpretation": sensitivity.get("annual_effect_interpretation"),
            "constraints": sensitivity.get("constraints", []),
        },
        "quality_gate": summary["quality_gate"],
        "boundaries": [
            "The screen evaluates mapped weather conditions only; surface fuel moisture and ground wind remain unmapped.",
            "The official district is not a burn unit, tenure, access or treatable-area mask.",
            "Threshold effects and block-bootstrap intervals are descriptive, not causal forecasts or operational validation.",
            "No count or rate is a burn approval, safety, treated-area, fire-risk or economic-value result.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--array-job-id", required=True)
    parser.add_argument("--aggregate-job-id", required=True)
    parser.add_argument("--array-elapsed-total-seconds", type=int, required=True)
    parser.add_argument("--array-max-rss-kib", type=int, required=True)
    parser.add_argument("--aggregate-elapsed-seconds", type=int, required=True)
    parser.add_argument("--aggregate-max-rss-kib", type=int, required=True)
    args = parser.parse_args()

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    result = build_public_record(
        summary,
        summary_file=args.summary.name,
        summary_sha256=_sha256(args.summary),
    )
    result["slurm_accounting"] = {
        "array_job_id": args.array_job_id,
        "aggregate_job_id": args.aggregate_job_id,
        "array_elapsed_total_seconds": args.array_elapsed_total_seconds,
        "array_max_rss_kib": args.array_max_rss_kib,
        "aggregate_elapsed_seconds": args.aggregate_elapsed_seconds,
        "aggregate_max_rss_kib": args.aggregate_max_rss_kib,
    }
    if (
        min(
            args.array_elapsed_total_seconds,
            args.array_max_rss_kib,
            args.aggregate_elapsed_seconds,
            args.aggregate_max_rss_kib,
        )
        <= 0
    ):
        parser.error("Slurm accounting values must be positive")
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
