"""Command-line interface for local validation and Spartan batch jobs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from .io import (
    ensure_hourly_grid,
    evaluate_xarray,
    inspect_dataset,
    normalise_dataset,
    open_climate_dataset,
    parse_chunks,
)
from .manifest import make_manifest, write_json, write_run_artifacts
from .models import MissingPolicy
from .rules import compilation_summary, load_prescriptions


def _select(prescriptions: list[object], name: str) -> object:
    matches = [item for item in prescriptions if item.burn_class == name]
    if not matches:
        options = [item.burn_class for item in prescriptions]
        raise ValueError(f"unknown burn class {name!r}; choose one of {options}")
    return matches[0]


def command_inspect(args: argparse.Namespace) -> int:
    prescriptions = load_prescriptions(args.prescriptions)
    report: dict[str, Any] = {"prescriptions": compilation_summary(prescriptions)}
    if args.input:
        dataset = open_climate_dataset(args.input, backend=args.backend, chunks=parse_chunks(args.chunks))
        dataset, warnings = normalise_dataset(dataset)
        report["climate"] = inspect_dataset(dataset)
        report["warnings"] = warnings
    else:
        report["climate"] = {"status": "not_supplied"}
    print(json.dumps(report, indent=2, default=str))
    if args.output:
        write_json(args.output, report)
    return 0


def command_analyse(args: argparse.Namespace) -> int:
    started = time.perf_counter()
    prescriptions = load_prescriptions(args.prescriptions)
    prescription = _select(prescriptions, args.burn_class)
    dataset = open_climate_dataset(args.input, backend=args.backend, chunks=parse_chunks(args.chunks))
    dataset, unit_warnings = normalise_dataset(dataset)
    if args.start or args.end:
        dataset = dataset.sel(time=slice(args.start, args.end))
    if dataset.sizes.get("time", 0) == 0:
        raise ValueError("time selection produced an empty dataset")
    dataset = ensure_hourly_grid(dataset)
    suitable, masks, rule_warnings = evaluate_xarray(
        dataset,
        prescription,
        missing_policy=MissingPolicy(args.missing_policy),
        include_unmapped=args.include_unmapped,
    )
    metrics: dict[str, Any] = {
        "evidence_status": f"verified-{args.data_kind}-by-this-run",
        "data_kind": args.data_kind,
        "burn_class": args.burn_class,
        "suitable_space_time_cells": int(suitable.sum().compute()),
        "evaluated_space_time_cells": int(suitable.count().compute()),
        "suitable_rate": float(suitable.mean().compute()),
        "condition_failure_rates": {
            key: float((~mask).mean().compute()) for key, mask in masks.items()
        },
        "minimum_duration_endpoints": {},
        "warnings": [*unit_warnings, *rule_warnings],
    }
    for duration in args.durations:
        endpoints = suitable.rolling(time=duration, min_periods=duration).sum() == duration
        metrics["minimum_duration_endpoints"][str(duration)] = int(endpoints.sum().compute())
    metrics["wall_seconds"] = time.perf_counter() - started
    manifest = make_manifest(
        command=sys.argv,
        input_paths=[args.prescriptions, args.input],
        config={
            "backend": args.backend,
            "chunks": parse_chunks(args.chunks),
            "missing_policy": args.missing_policy,
            "durations": args.durations,
            "include_unmapped": args.include_unmapped,
            "start": args.start,
            "end": args.end,
        },
        data_kind=args.data_kind,
    )
    write_run_artifacts(args.output_dir, manifest=manifest, metrics=metrics)
    print(json.dumps(metrics, indent=2, default=str))
    return 0


def command_benchmark(args: argparse.Namespace) -> int:
    import dask.array as da

    rng = np.random.default_rng(args.seed)
    shape = (args.hours, args.cells)
    temperature = rng.normal(20.0, 5.0, size=shape).astype("float32")
    humidity = rng.normal(50.0, 15.0, size=shape).astype("float32")
    wind = rng.gamma(2.0, 5.0, size=shape).astype("float32")
    started = time.perf_counter()
    numpy_result = ((temperature >= 15) & (temperature <= 25) & (humidity >= 35) & (humidity <= 60) & (wind <= 20)).mean()
    numpy_seconds = time.perf_counter() - started
    started = time.perf_counter()
    chunk = (min(args.chunk_hours, args.hours), min(args.chunk_cells, args.cells))
    dask_expression = (
        (da.from_array(temperature, chunks=chunk) >= 15)
        & (da.from_array(temperature, chunks=chunk) <= 25)
        & (da.from_array(humidity, chunks=chunk) >= 35)
        & (da.from_array(humidity, chunks=chunk) <= 60)
        & (da.from_array(wind, chunks=chunk) <= 20)
    ).mean()
    dask_result = (
        dask_expression.compute()
        if args.scheduler == "distributed"
        else dask_expression.compute(scheduler=args.scheduler)
    )
    dask_seconds = time.perf_counter() - started
    if not np.isclose(numpy_result, dask_result):
        raise RuntimeError("Dask and NumPy results differ")
    metrics = {
        "data_kind": "deterministic-synthetic-benchmark",
        "shape": list(shape),
        "seed": args.seed,
        "chunk": list(chunk),
        "scheduler": args.scheduler,
        "suitable_rate": float(numpy_result),
        "numpy_seconds": numpy_seconds,
        "dask_seconds": dask_seconds,
        "results_equal": True,
    }
    manifest = make_manifest(
        command=sys.argv,
        config=vars(args),
        data_kind="deterministic-synthetic-benchmark",
    )
    write_run_artifacts(args.output_dir, manifest=manifest, metrics=metrics)
    print(json.dumps(metrics, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="burn-window")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="validate prescriptions and optional climate data")
    inspect_parser.add_argument("--prescriptions", type=Path, required=True)
    inspect_parser.add_argument("--input", type=str)
    inspect_parser.add_argument("--backend", choices=["netcdf", "zarr", "kerchunk"], default="netcdf")
    inspect_parser.add_argument("--chunks", help='JSON, for example {"time":168,"lat":64,"lon":64}')
    inspect_parser.add_argument("--output", type=Path)
    inspect_parser.set_defaults(handler=command_inspect)

    analyse = subparsers.add_parser("analyse", help="run one burn-class analysis with provenance")
    analyse.add_argument("--prescriptions", type=Path, required=True)
    analyse.add_argument("--input", type=str, required=True)
    analyse.add_argument("--burn-class", required=True)
    analyse.add_argument("--output-dir", type=Path, required=True)
    analyse.add_argument("--backend", choices=["netcdf", "zarr", "kerchunk"], default="netcdf")
    analyse.add_argument("--chunks")
    analyse.add_argument("--durations", nargs="+", type=int, default=[2, 4, 6])
    analyse.add_argument("--missing-policy", choices=[item.value for item in MissingPolicy], default="error")
    analyse.add_argument("--include-unmapped", action="store_true")
    analyse.add_argument("--data-kind", choices=["real", "synthetic"], required=True)
    analyse.add_argument("--start", help="inclusive ISO time bound")
    analyse.add_argument("--end", help="inclusive ISO time bound")
    analyse.set_defaults(handler=command_analyse)

    benchmark = subparsers.add_parser("benchmark", help="compare NumPy and Dask on fixed synthetic data")
    benchmark.add_argument("--hours", type=int, default=8760)
    benchmark.add_argument("--cells", type=int, default=512)
    benchmark.add_argument("--chunk-hours", type=int, default=168)
    benchmark.add_argument("--chunk-cells", type=int, default=128)
    benchmark.add_argument(
        "--scheduler",
        choices=["threads", "processes", "synchronous", "distributed"],
        default="threads",
    )
    benchmark.add_argument("--seed", type=int, default=20260818)
    benchmark.add_argument("--output-dir", type=Path, required=True)
    benchmark.set_defaults(handler=command_benchmark)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, KeyError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
