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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run",
        action="append",
        required=True,
        metavar="WORKERS=METRICS_JSON",
    )
    parser.add_argument("--output", type=Path, required=True)
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
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
