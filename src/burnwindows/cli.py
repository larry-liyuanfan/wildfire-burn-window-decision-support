"""Command-line interface for local validation and Spartan batch jobs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from .aggregate import aggregate_vicclim6_years
from .io import (
    ensure_hourly_grid,
    evaluate_xarray,
    inspect_dataset,
    normalise_dataset,
    open_climate_dataset,
    open_vicclim6_period,
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
    if args.backend == "vicclim6":
        if not args.start or not args.end:
            raise ValueError("vicclim6 backend requires --start and --end")
        dataset = open_vicclim6_period(
            args.input,
            start=args.start,
            end=args.end,
            chunks=parse_chunks(args.chunks),
        )
    else:
        dataset = open_climate_dataset(
            args.input,
            backend=args.backend,
            chunks=parse_chunks(args.chunks),
        )
    dataset, unit_warnings = normalise_dataset(dataset)
    if args.start or args.end:
        dataset = dataset.sel(time=slice(args.start, args.end))
    if dataset.sizes.get("time", 0) == 0:
        raise ValueError("time selection produced an empty dataset")
    dataset = ensure_hourly_grid(dataset)
    suitable_with_context, masks_with_context, rule_warnings = evaluate_xarray(
        dataset,
        prescription,
        missing_policy=MissingPolicy(args.missing_policy),
        include_unmapped=args.include_unmapped,
    )
    metric_start = args.metric_start or args.start
    metric_end = args.metric_end or args.end
    suitable = suitable_with_context.sel(time=slice(metric_start, metric_end))
    masks = {
        key: value.sel(time=slice(metric_start, metric_end))
        for key, value in masks_with_context.items()
    }
    if suitable.sizes.get("time", 0) == 0:
        raise ValueError("metric time selection produced an empty dataset")
    excluded_unmapped = sum(
        condition.operational_status == "unmapped" and not args.include_unmapped
        for condition in prescription.conditions
    )
    prescription_complete = excluded_unmapped == 0 and not prescription.unresolved
    scope_warning = (
        []
        if prescription_complete
        else [
            (
                "partial prescription: unmapped conditions and unresolved source values are "
                "not evaluated; pass counts are not operational burn windows or safety evidence"
            )
        ]
    )
    metrics: dict[str, Any] = {
        "evidence_status": (
            f"verified-{args.data_kind}-complete-prescription-by-this-run"
            if prescription_complete
            else f"verified-{args.data_kind}-partial-prescription-by-this-run"
        ),
        "data_kind": args.data_kind,
        "burn_class": args.burn_class,
        "prescription_scope": {
            "complete": prescription_complete,
            "compiled_condition_count": len(prescription.conditions),
            "evaluated_condition_count": len(masks),
            "excluded_unmapped_condition_count": excluded_unmapped,
            "unresolved_value_count": len(prescription.unresolved),
        },
        "interpretation": (
            "complete compiled prescription evaluation"
            if prescription_complete
            else "provisional mapped-condition screen; not an operational burn window"
        ),
        "time_coverage": {
            "load_start": args.start,
            "load_end": args.end,
            "metric_start": metric_start,
            "metric_end": metric_end,
            "metric_hours": int(suitable.sizes["time"]),
            "left_censored": bool(metric_start == args.start),
        },
        "suitable_space_time_cells": int(suitable.sum().compute()),
        "evaluated_space_time_cells": int(suitable.count().compute()),
        "suitable_rate": float(suitable.mean().compute()),
        "condition_failure_counts": {
            key: int((~mask).sum().compute()) for key, mask in masks.items()
        },
        "condition_failure_rates": {
            key: float((~mask).mean().compute()) for key, mask in masks.items()
        },
        "minimum_duration_endpoints": {},
        "warnings": [*unit_warnings, *rule_warnings, *scope_warning],
    }
    for duration in args.durations:
        endpoints = (
            suitable_with_context.rolling(time=duration, min_periods=duration).sum()
            == duration
        ).sel(time=slice(metric_start, metric_end))
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
            "metric_start": metric_start,
            "metric_end": metric_end,
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


def command_aggregate_vicclim6(args: argparse.Namespace) -> int:
    years = range(args.year_start, args.year_end + 1)
    summary = aggregate_vicclim6_years(args.input, expected_years=years)
    write_json(args.output, summary)
    print(json.dumps(summary, indent=2, default=str))
    return 0


def command_inventory(args: argparse.Namespace) -> int:
    from .inventory import inventory_netcdf

    report = inventory_netcdf(args.input, sample_count=args.sample_count)
    manifest = make_manifest(
        command=sys.argv,
        input_paths=[args.input],
        config={"sample_count": args.sample_count},
        data_kind="real-data-metadata-inventory",
    )
    write_run_artifacts(args.output_dir, manifest=manifest, metrics=report)
    print(json.dumps(report, indent=2, default=str))
    return 0


def command_decision_benchmark(args: argparse.Namespace) -> int:
    from .decision_benchmark import run_decision_benchmark_suite

    metrics = run_decision_benchmark_suite(
        seed=args.seed,
        repetitions=args.repetitions,
        held_out_scenarios=args.held_out_scenarios,
        crew_capacity=args.crew_capacity,
        daily_capacity=args.daily_capacity,
    )
    manifest = make_manifest(
        command=sys.argv,
        config=vars(args),
        data_kind="deterministic-synthetic-operations-benchmark",
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

    inventory = subparsers.add_parser(
        "inventory", help="record scale and representative headers without copying payload data"
    )
    inventory.add_argument("--input", type=Path, required=True)
    inventory.add_argument("--sample-count", type=int, default=3)
    inventory.add_argument("--output-dir", type=Path, required=True)
    inventory.set_defaults(handler=command_inventory)

    analyse = subparsers.add_parser("analyse", help="run one burn-class analysis with provenance")
    analyse.add_argument("--prescriptions", type=Path, required=True)
    analyse.add_argument("--input", type=str, required=True)
    analyse.add_argument("--burn-class", required=True)
    analyse.add_argument("--output-dir", type=Path, required=True)
    analyse.add_argument(
        "--backend",
        choices=["netcdf", "zarr", "kerchunk", "vicclim6"],
        default="netcdf",
    )
    analyse.add_argument("--chunks")
    analyse.add_argument("--durations", nargs="+", type=int, default=[2, 4, 6])
    analyse.add_argument("--missing-policy", choices=[item.value for item in MissingPolicy], default="error")
    analyse.add_argument("--include-unmapped", action="store_true")
    analyse.add_argument("--data-kind", choices=["real", "synthetic"], required=True)
    analyse.add_argument("--start", help="inclusive ISO time bound")
    analyse.add_argument("--end", help="inclusive ISO time bound")
    analyse.add_argument(
        "--metric-start",
        help="inclusive metric bound; earlier loaded hours are context only",
    )
    analyse.add_argument(
        "--metric-end",
        help="inclusive metric bound; later loaded hours are context only",
    )
    analyse.set_defaults(handler=command_analyse)

    aggregate = subparsers.add_parser(
        "aggregate-vicclim6",
        help="quality-gate and aggregate restartable annual VicClim6 artifacts",
    )
    aggregate.add_argument("--input", type=Path, required=True)
    aggregate.add_argument("--year-start", type=int, required=True)
    aggregate.add_argument("--year-end", type=int, required=True)
    aggregate.add_argument("--output", type=Path, required=True)
    aggregate.set_defaults(handler=command_aggregate_vicclim6)

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

    decision = subparsers.add_parser(
        "decision-benchmark",
        help="compare greedy, nominal MILP and robust MILP on fixed synthetic operations scenarios",
    )
    decision.add_argument("--seed", type=int, default=20260819)
    decision.add_argument("--repetitions", type=int, default=30)
    decision.add_argument("--held-out-scenarios", type=int, default=200)
    decision.add_argument("--crew-capacity", type=int, default=2)
    decision.add_argument("--daily-capacity", type=int, default=3)
    decision.add_argument("--output-dir", type=Path, required=True)
    decision.set_defaults(handler=command_decision_benchmark)
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
