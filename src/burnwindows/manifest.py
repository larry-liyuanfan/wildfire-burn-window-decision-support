"""Machine-readable provenance for every benchmark or analysis run."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while block := handle.read(block_size):
            digest.update(block)
    return digest.hexdigest()


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def make_manifest(
    *,
    command: list[str],
    input_paths: Iterable[str | Path] = (),
    config: dict[str, Any] | None = None,
    data_kind: str,
) -> dict[str, Any]:
    inputs = []
    for raw in input_paths:
        path = Path(raw)
        inputs.append(
            {
                "path": str(path.resolve()),
                "sha256": sha256_file(path) if path.is_file() else None,
                "exists": path.exists(),
            }
        )
    return {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha(),
        "command": command,
        "inputs": inputs,
        "config": config or {},
        "data_kind": data_kind,
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "hostname": platform.node(),
            "cpu_count": os.cpu_count(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        },
    }


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def write_run_artifacts(
    output_dir: str | Path,
    *,
    manifest: dict[str, Any],
    metrics: dict[str, Any],
    errors: list[dict[str, Any]] | None = None,
) -> None:
    output = Path(output_dir)
    write_json(output / "run_manifest.json", manifest)
    write_json(output / "metrics.json", metrics)
    write_json(output / "error_cases.json", errors or [])

