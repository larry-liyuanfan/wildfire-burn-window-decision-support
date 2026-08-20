"""Verify that a controlled stop/resume preserves weather-screen semantics."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SEMANTIC_KEYS = (
    "screen_kind",
    "source",
    "store",
    "rule_source",
    "git_sha",
    "selection",
    "dimensions",
    "conditions",
    "unresolved",
    "warnings",
    "summary",
    "boundary",
)


def semantic_payload(metrics: dict[str, Any]) -> dict[str, Any]:
    missing = [key for key in SEMANTIC_KEYS if key not in metrics]
    if missing:
        raise ValueError(f"weather-screen metrics are missing semantic keys: {missing}")
    return {key: metrics[key] for key in SEMANTIC_KEYS}


def canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compare(baseline: dict[str, Any], resumed: dict[str, Any]) -> dict[str, Any]:
    baseline_semantic = semantic_payload(baseline)
    resumed_semantic = semantic_payload(resumed)
    equivalent = baseline_semantic == resumed_semantic
    if not equivalent:
        changed = [key for key in SEMANTIC_KEYS if baseline_semantic[key] != resumed_semantic[key]]
        raise ValueError(f"restart semantic equivalence failed: {changed}")
    baseline_resume_hours = int(baseline["streaming"]["resumed_from_hours"])
    resumed_from_hours = int(resumed["streaming"]["resumed_from_hours"])
    if baseline_resume_hours != 0 or resumed_from_hours <= 0:
        raise ValueError("restart provenance does not show a baseline and a resumed run")
    return {
        "evidence_status": "verified-real-public-reanalysis-if-run-completes",
        "restart_semantic_equivalence": True,
        "semantic_sha256": canonical_sha256(baseline_semantic),
        "baseline_resumed_from_hours": baseline_resume_hours,
        "controlled_run_resumed_from_hours": resumed_from_hours,
        "processed_hours": int(baseline["dimensions"]["time"]),
        "evaluated_cell_hours": int(baseline["summary"]["evaluated_cell_hours"]),
        "baseline_elapsed_seconds": float(baseline["elapsed_seconds"]),
        "resumed_segment_elapsed_seconds": float(resumed["elapsed_seconds"]),
        "boundary": (
            "This proves semantic equivalence after a controlled restart on a bounded public "
            "ERA5 weather-only screen. It does not validate VicClim6, burn suitability, safety, "
            "treated area, economic value, or recovery from every failure mode."
        ),
    }


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--resumed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    resumed = json.loads(args.resumed.read_text(encoding="utf-8"))
    result = compare(baseline, resumed)
    args.output.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output / "metrics.json"
    metrics_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "baseline_metrics_sha256": hashlib.sha256(args.baseline.read_bytes()).hexdigest(),
        "resumed_metrics_sha256": hashlib.sha256(args.resumed.read_bytes()).hexdigest(),
        "gate_metrics_sha256": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
    }
    (args.output / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(json.dumps({"metrics": result, "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
