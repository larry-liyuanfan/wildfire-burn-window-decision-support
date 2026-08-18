"""Build a versioned Kerchunk reference without copying climate payloads."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--concat-dim", default="time")
    args = parser.parse_args()

    from kerchunk.combine import MultiZarrToZarr
    from kerchunk.hdf import SingleHdf5ToZarr

    files = sorted(glob.glob(args.input_glob, recursive=True))
    if not files:
        parser.error(f"no files matched {args.input_glob}")
    references = [
        SingleHdf5ToZarr(path, path, inline_threshold=300).translate() for path in files
    ]
    combined = MultiZarrToZarr(
        references,
        concat_dims=[args.concat_dim],
        identical_dims=["lat", "lon"],
    ).translate()
    combined["burn_window_metadata"] = {
        "source_file_count": len(files),
        "payload_copied": False,
        "warning": "References inherit source access controls and must not be published blindly.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(combined), encoding="utf-8")
    print(f"wrote {args.output} for {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

