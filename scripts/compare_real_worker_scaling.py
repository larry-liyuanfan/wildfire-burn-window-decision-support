"""Build a compact, quality-gated record from completed real scaling runs."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from burnwindows.manifest import git_sha, write_json
from burnwindows.performance import compare_real_worker_scaling


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_run(path: Path, workers: int) -> tuple[dict, dict]:
    manifest_path = path.with_name("run_manifest.json")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing sibling run manifest for workers={workers}")
    metrics = json.loads(path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metrics["git_sha"] = manifest.get("git_sha")
    return metrics, {
        "dask_thread_workers": workers,
        "metrics_file": path.name,
        "metrics_sha256": _sha256(path),
        "manifest_file": manifest_path.name,
        "manifest_sha256": _sha256(manifest_path),
    }


def _parse_slurm_accounting(values: list[str], workers: set[int]) -> list[dict]:
    records = []
    for raw in values:
        worker_text, separator, payload = raw.partition("=")
        fields = payload.split(",") if separator else []
        if len(fields) != 3:
            raise ValueError(
                f"invalid --slurm {raw!r}; expected WORKERS=JOB_ID,ELAPSED_SECONDS,MAXRSS_KIB"
            )
        worker_count = int(worker_text)
        elapsed_seconds = int(fields[1])
        max_rss_kib = int(fields[2])
        if elapsed_seconds <= 0 or max_rss_kib <= 0:
            raise ValueError("Slurm elapsed time and MaxRSS must be positive")
        records.append(
            {
                "dask_thread_workers": worker_count,
                "job_id": fields[0],
                "elapsed_seconds": elapsed_seconds,
                "max_rss_kib": max_rss_kib,
            }
        )
    if records and {record["dask_thread_workers"] for record in records} != workers:
        raise ValueError("Slurm accounting must cover the same worker set as metrics")
    return sorted(records, key=lambda item: item["dask_thread_workers"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="WORKERS=METRICS_JSON",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--slurm",
        action="append",
        default=[],
        metavar="WORKERS=JOB_ID,ELAPSED_SECONDS,MAXRSS_KIB",
    )
    args = parser.parse_args()

    records = {}
    inputs = []
    for raw in args.run:
        worker_text, separator, path_text = raw.partition("=")
        if not separator:
            parser.error(f"invalid --run {raw!r}; expected WORKERS=METRICS_JSON")
        path = Path(path_text)
        workers = int(worker_text)
        records[workers], input_record = _load_run(path, workers)
        inputs.append(input_record)

    result = compare_real_worker_scaling(records)
    result["comparator_git_sha"] = git_sha()
    result["inputs"] = sorted(inputs, key=lambda item: item["dask_thread_workers"])
    if args.slurm:
        result["slurm_accounting"] = _parse_slurm_accounting(args.slurm, set(records))
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
