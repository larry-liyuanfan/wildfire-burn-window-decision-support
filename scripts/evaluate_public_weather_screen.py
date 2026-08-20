"""Run a public ERA5 historical weather-only necessary-condition screen."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr

from burnwindows.io import evaluate_xarray
from burnwindows.public_reanalysis import (
    HISTORICAL_WEATHER_SCREEN_SOURCE,
    derive_public_fire_weather_fields,
    historical_weather_screen_prescription,
)
from burnwindows.weather_screen import StreamingWeatherScreenSummary

STORE = "gs://gcp-public-data-arco-era5/ar/full_37-1h-0p25deg-chunk-1.zarr-v3"
SOURCE = "https://github.com/google-research/arco-era5"
VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    # The conservative shared adapter validates and emits precipitation even
    # though this partial screen does not apply the unresolved rain-history rule.
    "total_precipitation",
]


def _ordered_slice(values: Any, low: float, high: float) -> slice:
    return slice(low, high) if float(values[0]) <= float(values[-1]) else slice(high, low)


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", default="2024-03-01T00:00:00")
    parser.add_argument("--hours", type=int, default=168)
    parser.add_argument("--max-hours", type=int, default=8784)
    parser.add_argument("--chunk-hours", type=int, default=168)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if not 24 <= args.hours <= args.max_hours:
        raise SystemExit("hours must be between 24 and max-hours")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.chunk_hours < 24:
        raise SystemExit("chunk-hours must be at least 24")
    started = time.perf_counter()
    git_sha = _git_sha()
    checkpoint_path = args.output / "checkpoint.json"
    accumulator = StreamingWeatherScreenSummary()
    resumed_from_hours = 0
    if checkpoint_path.exists():
        if not args.resume:
            raise RuntimeError("checkpoint exists; pass --resume or choose a new output directory")
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        expected_config = {"start": args.start, "hours": args.hours, "git_sha": git_sha}
        if checkpoint.get("run_config") != expected_config:
            raise RuntimeError("checkpoint run configuration does not match this invocation")
        accumulator = StreamingWeatherScreenSummary.from_checkpoint(checkpoint["accumulator"])
        resumed_from_hours = accumulator.processed_hours

    dataset = xr.open_zarr(STORE, chunks=None, storage_options={"token": "anon"})
    missing = sorted(set(VARIABLES) - set(dataset.data_vars))
    if missing:
        raise RuntimeError(f"ARCO-ERA5 variable gate failed: {missing}")
    start = datetime.fromisoformat(args.start).replace(tzinfo=None)
    end = start + timedelta(hours=args.hours - 1)
    prescription = historical_weather_screen_prescription()
    warnings: set[str] = set()
    latitude_range: list[float] | None = None
    longitude_range: list[float] | None = None
    while accumulator.processed_hours < args.hours:
        offset = accumulator.processed_hours
        chunk_size = min(args.chunk_hours, args.hours - offset)
        chunk_start = start + timedelta(hours=offset)
        chunk_end = chunk_start + timedelta(hours=chunk_size - 1)
        subset = dataset[VARIABLES].sel(
            time=slice(chunk_start.isoformat(), chunk_end.isoformat()),
            latitude=_ordered_slice(dataset.latitude.values, -39.5, -34.0),
            longitude=_ordered_slice(dataset.longitude.values, 140.5, 150.5),
        ).load()
        if subset.sizes.get("time") != chunk_size:
            raise RuntimeError(
                f"hour coverage gate failed at offset {offset}: "
                f"{subset.sizes.get('time')} != {chunk_size}"
            )
        derived = derive_public_fire_weather_fields(subset)
        suitable, masks, chunk_warnings = evaluate_xarray(derived, prescription)
        accumulator.update(
            np.asarray(suitable.values),
            derived.time.values,
            {name: np.asarray(mask.values) for name, mask in masks.items()},
        )
        warnings.update(str(warning) for warning in chunk_warnings)
        latitude_range = [float(derived.latitude.min()), float(derived.latitude.max())]
        longitude_range = [float(derived.longitude.min()), float(derived.longitude.max())]
        checkpoint = {
            "run_config": {"start": args.start, "hours": args.hours, "git_sha": git_sha},
            "accumulator": accumulator.checkpoint(),
        }
        temporary = checkpoint_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(checkpoint), encoding="utf-8")
        temporary.replace(checkpoint_path)
        print(
            json.dumps(
                {
                    "event": "chunk_completed",
                    "processed_hours": accumulator.processed_hours,
                    "total_hours": args.hours,
                }
            ),
            flush=True,
        )

    summary = accumulator.summary()
    assert accumulator.grid_shape is not None
    metrics = {
        "evidence_status": "verified-real-public-reanalysis-if-run-completes",
        "screen_kind": "historical-public-weather-only-necessary-condition-screen",
        "source": SOURCE,
        "store": STORE,
        "rule_source": HISTORICAL_WEATHER_SCREEN_SOURCE,
        "git_sha": git_sha,
        "selection": {
            "time": [start.isoformat(), end.isoformat()],
            "latitude": latitude_range,
            "longitude": longitude_range,
        },
        "dimensions": {
            "time": args.hours,
            "latitude": accumulator.grid_shape[0],
            "longitude": accumulator.grid_shape[1],
        },
        "conditions": [condition.model_dump(mode="json") for condition in prescription.conditions],
        "unresolved": prescription.unresolved,
        "warnings": sorted(warnings),
        "summary": summary,
        "streaming": {
            "chunk_hours": args.chunk_hours,
            "resumed_from_hours": resumed_from_hours,
            "checkpoint": str(checkpoint_path),
        },
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "boundary": (
            "This is an upper-bound weather-only necessary-condition screen using historical "
            "published criteria. Missing FFDI, next-day FFDI, FFFI, rain-history, fuel moisture, "
            "site and burn-plan constraints prohibit calling passes burn windows, safe days, "
            "operational recommendations, treated area or economic value."
        ),
    }
    metrics_path = args.output / "metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "git_sha": metrics["git_sha"],
        "metrics_sha256": hashlib.sha256(metrics_path.read_bytes()).hexdigest(),
        "source": SOURCE,
        "store": STORE,
        "rule_source": HISTORICAL_WEATHER_SCREEN_SOURCE,
    }
    (args.output / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"metrics": metrics, "manifest": manifest}, indent=2))


if __name__ == "__main__":
    main()
