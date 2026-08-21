"""Publish a compact cost comparison from two verified FLARE run records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from burnwindows.manifest import write_json
from burnwindows.performance import compare_spatial_scope_performance


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--statewide", type=Path, required=True)
    parser.add_argument("--regional", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compare_spatial_scope_performance(_load(args.statewide), _load(args.regional))
    result = {
        "artifact_type": "vicclim6_spatial_scope_performance_comparison",
        "evidence_status": "verified-derived-from-public-real-run-records",
        "inputs": {
            "statewide_sha256": hashlib.sha256(args.statewide.read_bytes()).hexdigest(),
            "regional_sha256": hashlib.sha256(args.regional.read_bytes()).hexdigest(),
        },
        **result,
    }
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
