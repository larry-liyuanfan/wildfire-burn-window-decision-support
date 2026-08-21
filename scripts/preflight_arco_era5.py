"""Fetch a bounded anonymous ARCO-ERA5 slice as a real-data engineering gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import xarray as xr

from burnwindows.public_reanalysis import derive_public_fire_weather_fields

STORE = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
SOURCE = "https://github.com/google-research/arco-era5"
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "total_precipitation",
]


def _ordered_slice(values: Any, low: float, high: float) -> slice:
    return slice(low, high) if float(values[0]) <= float(values[-1]) else slice(high, low)


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2024-02-01T00:00:00")
    parser.add_argument("--hours", type=int, default=24)
    args = parser.parse_args()
    if not 1 <= args.hours <= 168:
        raise SystemExit("hours must be between 1 and 168 for the bounded preflight")
    args.output.mkdir(parents=True, exist_ok=True)

    dataset = xr.open_zarr(
        STORE,
        chunks=None,
        storage_options={"token": "anon"},
    )
    missing = sorted(set(VARIABLES) - set(dataset.data_vars))
    if missing:
        raise RuntimeError(f"ARCO-ERA5 variable gate failed: {missing}")
    start = datetime.fromisoformat(args.start).replace(tzinfo=None)
    end = start + timedelta(hours=args.hours - 1)
    subset = dataset[VARIABLES].sel(
        time=slice(start.isoformat(), end.isoformat()),
        latitude=_ordered_slice(dataset.latitude.values, -39.5, -34.0),
        longitude=_ordered_slice(dataset.longitude.values, 140.5, 150.5),
    )
    subset = subset.load()
    if subset.sizes.get("time") != args.hours:
        raise RuntimeError(f"hour coverage gate failed: {subset.sizes.get('time')} != {args.hours}")
    derived = derive_public_fire_weather_fields(subset)
    output_path = args.output / "arco_era5_victoria_preflight.nc"
    derived.to_netcdf(output_path, engine="h5netcdf")
    metrics = {
        "evidence_status": "verified-real-public-reanalysis-if-run-completes",
        "source": SOURCE,
        "store": STORE,
        "source_attrs": {
            key: str(dataset.attrs.get(key, ""))
            for key in ("valid_time_start", "valid_time_stop", "valid_time_stop_era5t", "last_updated")
        },
        "selection": {
            "time": [str(derived.time.values[0]), str(derived.time.values[-1])],
            "latitude": [float(derived.latitude.min()), float(derived.latitude.max())],
            "longitude": [float(derived.longitude.min()), float(derived.longitude.max())],
        },
        "dimensions": {str(key): int(value) for key, value in derived.sizes.items()},
        "variables": sorted(str(name) for name in derived.data_vars),
        "derived_file_bytes": output_path.stat().st_size,
        "derived_file_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "boundary": "Anonymous public ERA5 engineering preflight at 0.25 degrees. It does not replace 4 km VicClim6, validate FMS prescriptions, or derive FFDI/KBDI, trends, burn-window rates or economic value.",
    }
    (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": _git_sha(),
        "metrics_sha256": hashlib.sha256((args.output / "metrics.json").read_bytes()).hexdigest(),
        "source": SOURCE,
        "store": STORE,
    }
    (args.output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"metrics": metrics, "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
