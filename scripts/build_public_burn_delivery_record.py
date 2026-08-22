"""Build one tracked, self-contained record from the official burn delivery run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    metrics_path = args.run_dir / "metrics.json"
    manifest_path = args.run_dir / "run_manifest.json"
    record = {
        "schema_version": "1.0",
        "scope": "official public FFMVic plan/outcome records and polygon overlap",
        "metrics": _read(metrics_path),
        "run": _read(manifest_path),
        "source_artifact_sha256": {
            "metrics": _sha256(metrics_path),
            "run_manifest": _sha256(manifest_path),
        },
        "publication_boundary": [
            "No raw ArcGIS payload or restricted project data is embedded.",
            "Crew and AUD values are planning proxies, not unit records or savings.",
            "Geometry overlap is descriptive and is not causal risk or safety evidence.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
