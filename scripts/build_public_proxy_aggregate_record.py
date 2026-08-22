"""Publish a redacted record for a 51-year proxy-complete VicClim6 aggregate."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def build_public_record(
    summary: dict[str, Any],
    *,
    summary_sha256: str,
    aggregation_git_sha: str,
    array_job_id: str,
    aggregate_job_id: str,
    array_elapsed_total_seconds: int,
    array_max_rss_kib: int,
    aggregate_elapsed_seconds: int,
    aggregate_max_rss_kib: int,
) -> dict[str, Any]:
    if summary.get("evidence_status") != (
        "verified-real-proxy-complete-prescription-by-this-run"
    ):
        raise ValueError("summary did not pass the real proxy-complete gate")
    if summary.get("year_count") != 51:
        raise ValueError("summary is not the expected 51-year contract")
    scope = summary.get("prescription_scope", {})
    if not scope.get("complete") or scope.get("excluded_unmapped_condition_count") != 0:
        raise ValueError("summary did not evaluate every compiled condition")
    if summary.get("derived_fuel_inputs", {}).get("observed_on_site") is not False:
        raise ValueError("fuel inputs are not explicitly identified as proxies")
    quality = summary.get("quality_gate", {})
    if not quality or not all(quality.values()):
        raise ValueError("one or more annual aggregate quality gates failed")

    public_summary = deepcopy(summary)
    if public_summary.get("region_scope", {}).get("source_path"):
        public_summary["region_scope"]["source_path"] = "official-district-boundary.geojson"
    return {
        "schema_version": "1.0",
        "artifact_type": "vicclim6_murray_goldfields_51y_proxy_complete",
        "summary": public_summary,
        "evidence_identity": {
            "annual_run_git_sha": summary["git_sha"],
            "aggregation_git_sha": aggregation_git_sha,
            "input_summary_sha256": summary_sha256,
        },
        "slurm_accounting": {
            "array_job_id": array_job_id,
            "aggregate_job_id": aggregate_job_id,
            "array_elapsed_total_seconds": array_elapsed_total_seconds,
            "array_max_rss_kib": array_max_rss_kib,
            "aggregate_elapsed_seconds": aggregate_elapsed_seconds,
            "aggregate_max_rss_kib": aggregate_max_rss_kib,
        },
        "publication_boundary": [
            "All compiled conditions are evaluated, but FMC and fuel-level wind are literature-derived proxies.",
            "VicClim6 has no precipitation field, so no rain guard was applied.",
            "District grid cells are not operational burn units or treatable area.",
            "Rates and trends are descriptive, not approval, safety, causal risk or economic outcomes.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--aggregation-git-sha", required=True)
    parser.add_argument("--array-job-id", required=True)
    parser.add_argument("--aggregate-job-id", required=True)
    parser.add_argument("--array-elapsed-total-seconds", type=int, required=True)
    parser.add_argument("--array-max-rss-kib", type=int, required=True)
    parser.add_argument("--aggregate-elapsed-seconds", type=int, required=True)
    parser.add_argument("--aggregate-max-rss-kib", type=int, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    record = build_public_record(
        summary,
        summary_sha256=hashlib.sha256(args.summary.read_bytes()).hexdigest(),
        aggregation_git_sha=args.aggregation_git_sha,
        array_job_id=args.array_job_id,
        aggregate_job_id=args.aggregate_job_id,
        array_elapsed_total_seconds=args.array_elapsed_total_seconds,
        array_max_rss_kib=args.array_max_rss_kib,
        aggregate_elapsed_seconds=args.aggregate_elapsed_seconds,
        aggregate_max_rss_kib=args.aggregate_max_rss_kib,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
