"""Build a redacted public record for a completed real fuel-input proxy run."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_public_record(
    metrics: dict[str, Any],
    manifest: dict[str, Any],
    *,
    metrics_sha256: str,
    manifest_sha256: str,
    elapsed: str,
    compute_max_rss_kib: int,
) -> dict[str, Any]:
    expected_status = "verified-real-proxy-complete-prescription-by-this-run"
    if metrics.get("evidence_status") != expected_status:
        raise ValueError("run did not pass the real proxy-complete evidence gate")
    scope = metrics.get("prescription_scope", {})
    if not scope.get("complete") or scope.get("excluded_unmapped_condition_count") != 0:
        raise ValueError("run did not evaluate every compiled prescription condition")
    derived = metrics.get("derived_fuel_inputs", {})
    if derived.get("observed_on_site") is not False:
        raise ValueError("proxy record must explicitly deny on-site observation")
    if manifest.get("git_sha") is None or manifest.get("runtime", {}).get("slurm_job_id") is None:
        raise ValueError("run identity is incomplete")

    inputs = manifest.get("inputs", [])
    workbook = next((item for item in inputs if str(item.get("path", "")).endswith(".xlsx")), {})
    boundary = next(
        (item for item in inputs if str(item.get("path", "")).endswith(".geojson")), {}
    )
    public_metrics = deepcopy(metrics)
    if public_metrics.get("region_scope", {}).get("source_path"):
        public_metrics["region_scope"]["source_path"] = "official-district-boundary.geojson"
    return {
        "schema_version": "1.0",
        "scope": "2020 Murray Goldfields real VicClim6 complete-condition proxy pilot",
        "metrics": public_metrics,
        "run": {
            "created_at_utc": manifest.get("created_at_utc"),
            "git_sha": manifest["git_sha"],
            "slurm_job_id": manifest["runtime"]["slurm_job_id"],
            "python": manifest["runtime"].get("python"),
            "elapsed": elapsed,
            "compute_max_rss_kib": compute_max_rss_kib,
            "input_identity": {
                "prescription_workbook_sha256": workbook.get("sha256"),
                "region_boundary_sha256": boundary.get("sha256"),
                "vicclim6_source": "authorised Group44 six-family file-backed collection",
            },
        },
        "source_artifact_sha256": {
            "metrics": metrics_sha256,
            "run_manifest": manifest_sha256,
        },
        "publication_boundary": [
            "FMC is a dry-fuel meteorological model ensemble, not an on-site reading.",
            "Fuel-level wind is an explicit wind-reduction-factor scenario, not site calibration.",
            "VicClim6 has no precipitation field, so the rain guard was not applied in this run.",
            "District cells are not burn-unit or treatable-area cells.",
            "The result is not burn authorisation, safety evidence, risk reduction or economic value.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--elapsed", required=True)
    parser.add_argument("--compute-max-rss-kib", type=int, required=True)
    args = parser.parse_args()
    metrics_path = args.run_dir / "metrics.json"
    manifest_path = args.run_dir / "run_manifest.json"
    record = build_public_record(
        _read(metrics_path),
        _read(manifest_path),
        metrics_sha256=_sha256(metrics_path),
        manifest_sha256=_sha256(manifest_path),
        elapsed=args.elapsed,
        compute_max_rss_kib=args.compute_max_rss_kib,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
