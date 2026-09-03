"""Command-line interface for local validation and Spartan batch jobs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np

from .aggregate import aggregate_vicclim6_years
from .burn_unit_climatology import (
    DEFAULT_DURATIONS,
    DEFAULT_THRESHOLDS,
    RAIN_GUARD_WARNING,
    BurnUnitClimatologyCatalog,
    SparseBurnOverlay,
    aggregate_annual_artifacts,
    aggregate_grid_year,
    compare_annual_recomputation,
    publish_compact_artifact,
    read_json,
    validate_compact_artifact,
)
from .engine import apply_threshold_scenario
from .fuel_inputs import add_xarray_fuel_inputs, promote_derived_conditions
from .io import (
    ensure_hourly_grid,
    evaluate_xarray,
    inspect_dataset,
    normalise_dataset,
    open_climate_dataset,
    open_vicclim6_period,
    parse_chunks,
)
from .manifest import git_sha, make_manifest, sha256_file, write_json, write_run_artifacts
from .models import MissingPolicy, Prescription
from .rules import compilation_summary, load_prescriptions
from .spatial import subset_rectilinear_geojson


def _select(prescriptions: list[Prescription], name: str) -> Prescription:
    matches = [item for item in prescriptions if item.burn_class == name]
    if not matches:
        options = [item.burn_class for item in prescriptions]
        raise ValueError(f"unknown burn class {name!r}; choose one of {options}")
    return matches[0]


def _load_threshold_scenarios(
    path: Path,
    prescription: Prescription,
) -> dict[str, dict[str, float]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("threshold-scenarios must be a non-empty JSON object")
    if len(payload) > 16:
        raise ValueError("threshold-scenarios is limited to 16 scenarios per run")

    result: dict[str, dict[str, float]] = {}
    for raw_name, raw_overrides in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise ValueError("threshold scenario names must be non-empty strings")
        name = raw_name.strip()
        if name == "baseline":
            raise ValueError("baseline is reserved and must not be supplied")
        if not isinstance(raw_overrides, dict) or not raw_overrides:
            raise ValueError(f"threshold scenario {name!r} needs field deltas")
        overrides: dict[str, float] = {}
        for field, raw_delta in raw_overrides.items():
            if not isinstance(field, str) or isinstance(raw_delta, bool):
                raise TypeError(f"invalid threshold override in scenario {name!r}")
            try:
                delta = float(raw_delta)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"threshold delta for {field!r} in {name!r} is not numeric"
                ) from exc
            if not np.isfinite(delta):
                raise ValueError(f"threshold delta for {field!r} in {name!r} is not finite")
            overrides[field] = delta
        # Validate mapped fields and range inversion before building any Dask graph.
        apply_threshold_scenario(prescription, overrides)
        result[name] = overrides
    return dict(sorted(result.items()))


def _decode_baseline_reductions(
    computed: tuple[object, ...],
    condition_names: list[str],
    duration_names: list[str],
) -> tuple[int, int, dict[str, int], dict[str, int]]:
    """Decode only baseline reductions even when scenario values follow them."""

    baseline_size = 2 + len(condition_names) + len(duration_names)
    if len(computed) < baseline_size:
        raise ValueError("Dask reduction result is shorter than the baseline contract")
    screened_cells = int(computed[0])
    evaluated_cells = int(computed[1])
    condition_start = 2
    duration_start = condition_start + len(condition_names)
    condition_values = computed[condition_start:duration_start]
    duration_values = computed[duration_start:baseline_size]
    condition_failure_counts = {
        name: int(value) for name, value in zip(condition_names, condition_values, strict=True)
    }
    duration_endpoints = {
        name: int(value) for name, value in zip(duration_names, duration_values, strict=True)
    }
    return screened_cells, evaluated_cells, condition_failure_counts, duration_endpoints


def command_inspect(args: argparse.Namespace) -> int:
    prescriptions = load_prescriptions(args.prescriptions)
    report: dict[str, Any] = {"prescriptions": compilation_summary(prescriptions)}
    if args.input:
        dataset = open_climate_dataset(
            args.input, backend=args.backend, chunks=parse_chunks(args.chunks)
        )
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
    import dask

    dask_workers = args.dask_workers or int(os.environ.get("SLURM_CPUS_PER_TASK", "1"))
    if dask_workers < 1:
        raise ValueError("dask-workers must be positive")
    dask.config.set(scheduler=args.scheduler, num_workers=dask_workers)
    started = time.perf_counter()
    prescriptions = load_prescriptions(args.prescriptions)
    prescription = _select(prescriptions, args.burn_class)
    if args.derive_fuel_proxies:
        prescription = promote_derived_conditions(prescription)
    threshold_scenarios = (
        _load_threshold_scenarios(args.threshold_scenarios, prescription)
        if args.threshold_scenarios
        else {}
    )
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
    region_scope = None
    if args.region_geojson:
        dataset, region_scope = subset_rectilinear_geojson(dataset, args.region_geojson)
        region_scope["label"] = args.region_label
    dataset, unit_warnings = normalise_dataset(dataset)
    derived_fuel_inputs = None
    if args.derive_fuel_proxies:
        dataset, derived_fuel_inputs, derived_warnings = add_xarray_fuel_inputs(
            dataset,
            wind_reduction_factor=args.wind_reduction_factor,
            rain_guard_mm=args.fmc_rain_guard_mm,
        )
        unit_warnings.extend(derived_warnings)
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
    scenario_suitable: dict[str, object] = {}
    scenario_suitable_with_context: dict[str, object] = {}
    scenario_warnings: dict[str, list[str]] = {}
    for name, overrides in threshold_scenarios.items():
        scenario_rule = apply_threshold_scenario(prescription, overrides)
        scenario_with_context, _, warnings = evaluate_xarray(
            dataset,
            scenario_rule,
            missing_policy=MissingPolicy(args.missing_policy),
            include_unmapped=args.include_unmapped,
        )
        scenario_suitable_with_context[name] = scenario_with_context
        scenario_suitable[name] = scenario_with_context.sel(time=slice(metric_start, metric_end))
        scenario_warnings[name] = warnings
    if suitable.sizes.get("time", 0) == 0:
        raise ValueError("metric time selection produced an empty dataset")
    excluded_unmapped = sum(
        condition.operational_status == "unmapped" and not args.include_unmapped
        for condition in prescription.conditions
    )
    prescription_complete = excluded_unmapped == 0 and not prescription.unresolved
    scope_warning = []
    if derived_fuel_inputs:
        scope_warning.append(
            "all compiled conditions are evaluated, but two inputs are literature-derived "
            "proxies rather than on-site measurements; results are not burn authorisation"
        )
    elif not prescription_complete:
        scope_warning.extend(
            [
                (
                    "partial prescription: unmapped conditions and unresolved source values are "
                    "not evaluated; pass counts are not operational burn windows or safety evidence"
                )
            ]
        )
    condition_names = list(masks)
    duration_names = [str(duration) for duration in args.durations]
    endpoint_tasks = [
        (suitable_with_context.rolling(time=duration, min_periods=duration).sum() == duration)
        .sel(time=slice(metric_start, metric_end))
        .sum()
        for duration in args.durations
    ]
    sensitivity_tasks: list[object] = []
    for name in threshold_scenarios:
        values = scenario_suitable[name]
        sensitivity_tasks.append(values.sum())
        sensitivity_tasks.extend(
            (
                scenario_suitable_with_context[name]
                .rolling(time=duration, min_periods=duration)
                .sum()
                == duration
            )
            .sel(time=slice(metric_start, metric_end))
            .sum()
            for duration in args.durations
        )
    computed = dask.compute(
        suitable.sum(),
        suitable.count(),
        *((~masks[name]).sum() for name in condition_names),
        *endpoint_tasks,
        *sensitivity_tasks,
    )
    (
        screened_cells,
        evaluated_cells,
        condition_failure_counts,
        duration_endpoints,
    ) = _decode_baseline_reductions(computed, condition_names, duration_names)
    sensitivity_cursor = 2 + len(condition_names) + len(duration_names)
    sensitivity_results: list[dict[str, Any]] = []
    for name, overrides in threshold_scenarios.items():
        scenario_cells = int(computed[sensitivity_cursor])
        sensitivity_cursor += 1
        scenario_endpoints = {
            duration: int(value)
            for duration, value in zip(
                duration_names,
                computed[sensitivity_cursor : sensitivity_cursor + len(duration_names)],
                strict=True,
            )
        }
        sensitivity_cursor += len(duration_names)
        scenario_rate = scenario_cells / evaluated_cells if evaluated_cells else 0.0
        baseline_rate = screened_cells / evaluated_cells if evaluated_cells else 0.0
        sensitivity_results.append(
            {
                "scenario": name,
                "overrides": overrides,
                "provisional_pass_cells": scenario_cells,
                "provisional_pass_rate": scenario_rate,
                "absolute_rate_change": scenario_rate - baseline_rate,
                "relative_rate_change": (
                    (scenario_rate - baseline_rate) / baseline_rate if baseline_rate else None
                ),
                "minimum_duration_endpoints": scenario_endpoints,
                "warnings": scenario_warnings[name],
            }
        )
    metrics: dict[str, Any] = {
        "evidence_status": (
            f"verified-{args.data_kind}-proxy-complete-prescription-by-this-run"
            if prescription_complete and derived_fuel_inputs
            else f"verified-{args.data_kind}-complete-prescription-by-this-run"
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
            "complete compiled-condition evaluation with literature-derived proxies"
            if derived_fuel_inputs and prescription_complete
            else "complete compiled prescription evaluation"
            if prescription_complete
            else "provisional mapped-condition screen; not an operational burn window"
        ),
        "derived_fuel_inputs": derived_fuel_inputs,
        "region_scope": region_scope,
        "time_coverage": {
            "load_start": args.start,
            "load_end": args.end,
            "metric_start": metric_start,
            "metric_end": metric_end,
            "scheduler": args.scheduler,
            "dask_workers": dask_workers,
            "metric_hours": int(suitable.sizes["time"]),
            "left_censored": bool(metric_start == args.start),
        },
        "suitable_space_time_cells": screened_cells,
        "evaluated_space_time_cells": evaluated_cells,
        "suitable_rate": screened_cells / evaluated_cells,
        "condition_failure_counts": condition_failure_counts,
        "condition_failure_rates": {
            key: count / evaluated_cells for key, count in condition_failure_counts.items()
        },
        "minimum_duration_endpoints": duration_endpoints,
        "warnings": [*unit_warnings, *rule_warnings, *scope_warning],
    }
    if sensitivity_results:
        metrics["threshold_sensitivity"] = {
            "semantics": (
                "field-specific absolute deltas in each rule's declared unit; "
                "positive widens and negative narrows the admissible interval"
            ),
            "source": str(args.threshold_scenarios),
            "baseline": {
                "provisional_pass_cells": screened_cells,
                "provisional_pass_rate": screened_cells / evaluated_cells,
                "minimum_duration_endpoints": duration_endpoints,
            },
            "scenarios": sensitivity_results,
            "constraints": [
                "scenario changes are descriptive threshold sensitivity, not forecasts",
                (
                    "fuel-moisture and fuel-level wind are literature-derived proxies"
                    if derived_fuel_inputs
                    else "unmapped fuel-moisture and ground-wind conditions remain excluded"
                ),
                "pass counts are not operational burn approvals or safety evidence",
            ],
        }
    metrics["wall_seconds"] = time.perf_counter() - started
    input_paths = [args.prescriptions, args.input]
    if args.region_geojson:
        input_paths.append(args.region_geojson)
    if args.threshold_scenarios:
        input_paths.append(args.threshold_scenarios)
    manifest = make_manifest(
        command=sys.argv,
        input_paths=input_paths,
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
            "region_geojson": str(args.region_geojson) if args.region_geojson else None,
            "region_label": args.region_label,
            "threshold_scenarios": (
                str(args.threshold_scenarios) if args.threshold_scenarios else None
            ),
            "derive_fuel_proxies": args.derive_fuel_proxies,
            "wind_reduction_factor": args.wind_reduction_factor,
            "fmc_rain_guard_mm": args.fmc_rain_guard_mm,
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
    numpy_result = (
        (temperature >= 15)
        & (temperature <= 25)
        & (humidity >= 35)
        & (humidity <= 60)
        & (wind <= 20)
    ).mean()
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
    summary["aggregation_git_sha"] = git_sha()
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


def command_official_outcomes(args: argparse.Namespace) -> int:
    from .official_burns import (
        build_delivery_summary,
        build_spatial_delivery_summary,
        fetch_district_delivery,
        fetch_matched_delivery_geometries,
    )

    plans, outcomes, provenance = fetch_district_delivery(
        planned_district=args.planned_district,
        history_district=args.history_district,
    )
    metrics = build_delivery_summary(plans, outcomes)
    metrics["provenance"] = provenance
    matched_ids = sorted({item.burn_id for item in plans} & {item.burn_id for item in outcomes})
    plan_geojson, outcome_geojson, geometry_provenance = fetch_matched_delivery_geometries(
        matched_ids
    )
    metrics["spatial_delivery"] = build_spatial_delivery_summary(plan_geojson, outcome_geojson)
    metrics["provenance"]["geometries"] = geometry_provenance
    manifest = make_manifest(
        command=sys.argv,
        config={
            "planned_district": args.planned_district,
            "history_district": args.history_district,
        },
        data_kind="official-public-burn-plan-and-outcome-records",
    )
    write_run_artifacts(args.output_dir, manifest=manifest, metrics=metrics)
    print(json.dumps(metrics, indent=2, default=str))
    return 0


def command_burn_unit_overlay(args: argparse.Namespace) -> int:
    import xarray as xr

    from .burn_units import build_area_weighted_overlay
    from .official_burns import PLANNED_BURNS_URL, fetch_arcgis_geojson

    if args.geojson:
        geojson = json.loads(args.geojson.read_text(encoding="utf-8"))
        provenance: dict[str, Any] = {"source_path": str(args.geojson.resolve())}
    else:
        geojson, provenance = fetch_arcgis_geojson(
            PLANNED_BURNS_URL,
            where=args.where,
            out_fields=["OBJECTID", "TREAT_NO", "TREAT_NAME", "HECTARES", "DISTRICT", "REGION"],
        )
    with xr.open_dataset(args.grid) as dataset:
        if args.latitude_name not in dataset.coords or args.longitude_name not in dataset.coords:
            raise ValueError("grid file lacks requested latitude/longitude coordinates")
        overlay = build_area_weighted_overlay(
            geojson,
            latitude=np.asarray(dataset[args.latitude_name].values),
            longitude=np.asarray(dataset[args.longitude_name].values),
            id_property=args.id_property,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "burn_unit_overlay.json", overlay)
    metrics = {
        key: overlay[key]
        for key in (
            "grid_shape",
            "burn_unit_count",
            "covered_burn_unit_count",
            "zero_coverage_burn_unit_count",
            "contract",
        )
    }
    metrics["weight_row_count"] = len(overlay["weights"])
    metrics["provenance"] = provenance
    manifest = make_manifest(
        command=sys.argv,
        input_paths=[args.grid, *([args.geojson] if args.geojson else [])],
        config={
            "where": args.where,
            "id_property": args.id_property,
            "latitude_name": args.latitude_name,
            "longitude_name": args.longitude_name,
        },
        data_kind="official-burn-unit-area-weighted-grid-overlay",
    )
    write_run_artifacts(args.output_dir, manifest=manifest, metrics=metrics)
    print(json.dumps(metrics, indent=2, default=str))
    return 0


def _all_condition_inputs_valid(dataset: object, prescription: Prescription) -> object:
    import xarray as xr

    template = next(iter(dataset.data_vars.values()))
    combined = xr.ones_like(template, dtype=bool)
    season_months = {
        "summer": [12, 1, 2],
        "autumn": [3, 4, 5],
        "winter": [6, 7, 8],
        "spring": [9, 10, 11],
    }
    for condition in prescription.conditions:
        if condition.operational_status == "unmapped":
            raise ValueError(f"condition remains unmapped: {condition.field}")
        if condition.variable not in dataset:
            raise ValueError(f"dataset lacks condition variable {condition.variable}")
        valid = dataset[condition.variable].notnull()
        if condition.season:
            active = dataset.time.dt.month.isin(season_months[condition.season])
            valid = xr.where(active, valid, True)
        combined &= valid
    return combined


def _compute_burn_unit_year(
    args: argparse.Namespace,
    *,
    method: Literal["sparse", "direct"],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    import dask
    import pandas as pd

    dask_workers = args.dask_workers or int(os.environ.get("SLURM_CPUS_PER_TASK", "1"))
    if dask_workers < 1:
        raise ValueError("dask-workers must be positive")
    dask.config.set(scheduler=args.scheduler, num_workers=dask_workers)
    overlay_payload = read_json(args.overlay)
    overlay = SparseBurnOverlay.from_mapping(
        overlay_payload,
        expected_burn_unit_count=args.expected_burn_units,
        expected_weight_row_count=args.expected_weight_rows,
    )
    spatial_sha256 = sha256_file(args.overlay)
    if args.expected_spatial_sha256 and spatial_sha256 != args.expected_spatial_sha256:
        raise ValueError(
            f"overlay SHA mismatch: expected {args.expected_spatial_sha256}, found {spatial_sha256}"
        )
    rule_sha256 = sha256_file(args.prescriptions)
    if args.expected_rule_sha256 and rule_sha256 != args.expected_rule_sha256:
        raise ValueError(
            f"workbook SHA mismatch: expected {args.expected_rule_sha256}, found {rule_sha256}"
        )

    prescriptions = load_prescriptions(args.prescriptions)
    prescription = promote_derived_conditions(_select(prescriptions, args.burn_class))
    remaining_unmapped = [
        condition.field
        for condition in prescription.conditions
        if condition.operational_status == "unmapped"
    ]
    if len(prescription.conditions) != 8 or prescription.unresolved or remaining_unmapped:
        raise ValueError(
            "burn-ID climatology requires one complete 8/8 compiled rule with no unresolved "
            f"values; conditions={len(prescription.conditions)}, "
            f"unresolved={prescription.unresolved}, unmapped={remaining_unmapped}"
        )

    year = int(args.year)
    metric_start = pd.Timestamp(year=year, month=1, day=1)
    if year == 1973:
        metric_start += pd.Timedelta(hours=24)
        load_start = metric_start
    else:
        load_start = metric_start - pd.Timedelta(hours=max(DEFAULT_DURATIONS) - 1)
    metric_end = pd.Timestamp(year=year, month=12, day=31, hour=23)
    dataset = open_vicclim6_period(
        args.input,
        start=load_start,
        end=metric_end,
        chunks=parse_chunks(args.chunks),
    )
    if (
        int(dataset.sizes.get("latitude", -1)),
        int(dataset.sizes.get("longitude", -1)),
    ) != overlay.grid_shape:
        raise ValueError(
            "VicClim6 grid shape differs from the pinned burn-unit overlay contract"
        )
    dataset = dataset.stack(
        spatial_cell=("latitude", "longitude"), create_index=False
    ).isel(spatial_cell=overlay.flat_grid_indices)
    dataset, unit_warnings = normalise_dataset(dataset)
    dataset, fuel_provenance, fuel_warnings = add_xarray_fuel_inputs(
        dataset,
        wind_reduction_factor=args.wind_reduction_factor,
        rain_guard_mm=args.fmc_rain_guard_mm,
    )
    dataset = ensure_hourly_grid(dataset)
    suitable_with_context, masks_with_context, rule_warnings = evaluate_xarray(
        dataset,
        prescription,
        missing_policy=MissingPolicy.ERROR,
        include_unmapped=False,
    )
    valid_with_context = _all_condition_inputs_valid(dataset, prescription)
    metric_slice = slice(metric_start, metric_end)
    suitable = suitable_with_context.sel(time=metric_slice)
    valid = valid_with_context.sel(time=metric_slice)
    masks = {name: values.sel(time=metric_slice) for name, values in masks_with_context.items()}
    if int(suitable.sizes.get("time", 0)) < 1:
        raise ValueError("annual metric selection is empty")
    computed = dask.compute(suitable, valid, *(masks[name] for name in masks))
    suitable_values = np.asarray(computed[0].values, dtype=bool)
    valid_values = np.asarray(computed[1].values, dtype=bool)
    condition_values = {
        name: np.asarray(value.values, dtype=bool)
        for name, value in zip(masks, computed[2:], strict=True)
    }
    warnings = sorted(
        {
            *unit_warnings,
            *fuel_warnings,
            *rule_warnings,
            (
                "all 8/8 compiled conditions are evaluated at grid level; FMC and ground wind "
                "remain literature-derived proxies"
            ),
            (
                "weighted area fractions and 0.5/0.8/1.0 thresholds are descriptive "
                "climatology, not operational approval"
            ),
        }
    )
    if RAIN_GUARD_WARNING not in warnings:
        raise ValueError("expected VicClim6 precipitation-unavailable warning was not emitted")
    code_sha = git_sha()
    records, hourly_fraction, valid_hours = aggregate_grid_year(
        year=year,
        overlay=overlay,
        suitable=suitable_values,
        all_conditions_valid=valid_values,
        condition_masks=condition_values,
        data_sha256=args.data_sha256,
        rule_sha256=rule_sha256,
        spatial_sha256=spatial_sha256,
        code_sha=code_sha,
        warnings=warnings,
        thresholds=DEFAULT_THRESHOLDS,
        durations=DEFAULT_DURATIONS,
        method=method,
    )
    weight_sums = overlay.weight_sums()
    metrics = {
        "schema_version": "1.0",
        "artifact_kind": "burn-unit-climatology-annual",
        "evidence_status": "verified-real-8-of-8-proxy-climatology-by-this-run",
        "year": year,
        "burn_class": args.burn_class,
        "metric_start": metric_start.isoformat(),
        "metric_end": metric_end.isoformat(),
        "metric_hours": int(suitable_values.shape[0]),
        "left_censored": year == 1973,
        "aggregation_method": method,
        "prescription_scope": {
            "compiled_condition_count": len(prescription.conditions),
            "evaluated_condition_count": len(condition_values),
            "unresolved_value_count": len(prescription.unresolved),
            "remaining_unmapped_condition_count": len(remaining_unmapped),
        },
        "derived_fuel_inputs": fuel_provenance,
        "spatial_contract": {
            "burn_unit_count": len(overlay.burn_ids),
            "source_weight_row_count": overlay.source_weight_row_count,
            "selected_unique_grid_cell_count": len(overlay.flat_grid_indices),
            "normalised_weight_sum_min": float(weight_sums.min()),
            "normalised_weight_sum_max": float(weight_sums.max()),
            "zero_coverage_burn_unit_count": overlay.zero_coverage_burn_unit_count,
            "nearest_cell_fallback_count": 0,
        },
        "provenance": {
            "data_sha256": args.data_sha256,
            "rule_sha256": rule_sha256,
            "spatial_sha256": spatial_sha256,
            "git_sha": code_sha,
        },
        "thresholds": list(DEFAULT_THRESHOLDS),
        "durations_hours": list(DEFAULT_DURATIONS),
        "warnings": warnings,
        "annual_records": records,
        "quality_gate": {
            "all_176_burn_ids": len(overlay.burn_ids) == 176,
            "all_351_nonzero_weights_used": overlay.source_weight_row_count == 351,
            "normalised_weight_sums_within_1e-6": bool(
                np.allclose(weight_sums, 1.0, atol=1e-6, rtol=0.0)
            ),
            "zero_nearest_cell_fallback": overlay.zero_coverage_burn_unit_count == 0,
            "complete_8_of_8_rule": len(condition_values) == 8,
            "rain_guard_warning_preserved": RAIN_GUARD_WARNING in warnings,
            "single_data_rule_spatial_and_git_sha": True,
        },
    }
    if not all(metrics["quality_gate"].values()):
        raise ValueError(f"annual quality gate failed: {metrics['quality_gate']}")
    return metrics, hourly_fraction, valid_hours


def _write_hourly_npz(
    path: Path,
    *,
    burn_ids: Sequence[str],
    hourly_fraction: np.ndarray,
    valid_hours: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        burn_ids=np.asarray(burn_ids),
        weighted_suitable_area_fraction=np.asarray(hourly_fraction, dtype=np.float64),
        valid_hours=np.asarray(valid_hours, dtype=bool),
    )


def command_burn_unit_year(args: argparse.Namespace) -> int:
    from .manifest import sha256_file

    started = time.perf_counter()
    try:
        metrics, hourly_fraction, valid_hours = _compute_burn_unit_year(
            args, method="sparse"
        )
        hourly_path = args.output_dir / "hourly_weighted_suitable_area_fraction.npz"
        _write_hourly_npz(
            hourly_path,
            burn_ids=[row["burn_id"] for row in metrics["annual_records"]],
            hourly_fraction=hourly_fraction,
            valid_hours=valid_hours,
        )
        metrics["hourly_artifact"] = {
            "filename": hourly_path.name,
            "sha256": sha256_file(hourly_path),
            "published_in_compact_artifact": False,
        }
        metrics["wall_seconds"] = time.perf_counter() - started
        manifest = make_manifest(
            command=sys.argv,
            input_paths=[args.prescriptions, args.overlay],
            config={
                "year": args.year,
                "data_sha256": args.data_sha256,
                "burn_class": args.burn_class,
                "chunks": parse_chunks(args.chunks),
                "scheduler": args.scheduler,
                "dask_workers": args.dask_workers,
                "wind_reduction_factor": args.wind_reduction_factor,
                "fmc_rain_guard_mm": args.fmc_rain_guard_mm,
                "expected_burn_units": args.expected_burn_units,
                "expected_weight_rows": args.expected_weight_rows,
            },
            data_kind="real",
        )
        write_run_artifacts(args.output_dir, manifest=manifest, metrics=metrics)
    except Exception as exc:
        write_json(
            args.output_dir / "quality_failure.json",
            {
                "status": "failed",
                "year": args.year,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "git_sha": git_sha(),
                "hidden": False,
            },
        )
        raise
    print(json.dumps({key: value for key, value in metrics.items() if key != "annual_records"}, indent=2))
    return 0


def command_compare_burn_unit_year(args: argparse.Namespace) -> int:
    try:
        expected = read_json(args.pilot_dir / "metrics.json")
        hourly_path = args.pilot_dir / str(expected["hourly_artifact"]["filename"])
        with np.load(hourly_path, allow_pickle=False) as arrays:
            expected_fraction = np.asarray(
                arrays["weighted_suitable_area_fraction"], dtype=np.float64
            )
            expected_valid = np.asarray(arrays["valid_hours"], dtype=bool)
        actual, actual_fraction, actual_valid = _compute_burn_unit_year(
            args, method="direct"
        )
        comparison = compare_annual_recomputation(
            expected_records=expected["annual_records"],
            expected_hourly_fraction=expected_fraction,
            expected_valid_hours=expected_valid,
            actual_records=actual["annual_records"],
            actual_hourly_fraction=actual_fraction,
            actual_valid_hours=actual_valid,
        )
        comparison["pilot_hourly_sha256"] = expected["hourly_artifact"]["sha256"]
        comparison["git_sha"] = git_sha()
        manifest = make_manifest(
            command=sys.argv,
            input_paths=[args.prescriptions, args.overlay, hourly_path],
            config={"year": args.year, "comparison": "direct-per-burn"},
            data_kind="real",
        )
        write_run_artifacts(args.output_dir, manifest=manifest, metrics=comparison)
    except Exception as exc:
        write_json(
            args.output_dir / "quality_failure.json",
            {
                "status": "failed",
                "year": args.year,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "git_sha": git_sha(),
                "hidden": False,
            },
        )
        raise
    print(json.dumps(comparison, indent=2))
    return 0


def command_burn_unit_preflight(args: argparse.Namespace) -> int:
    from .inventory import inventory_netcdf
    from .manifest import sha256_file

    overlay = SparseBurnOverlay.from_mapping(
        read_json(args.overlay),
        expected_burn_unit_count=args.expected_burn_units,
        expected_weight_row_count=args.expected_weight_rows,
    )
    prescriptions = load_prescriptions(args.prescriptions)
    prescription = promote_derived_conditions(_select(prescriptions, args.burn_class))
    inventory = inventory_netcdf(args.input, sample_count=3)
    result = {
        "status": "passed",
        "git_sha": git_sha(),
        "data_sha256": inventory["collection_metadata_sha256"],
        "rule_sha256": sha256_file(args.prescriptions),
        "spatial_sha256": sha256_file(args.overlay),
        "burn_unit_count": len(overlay.burn_ids),
        "weight_row_count": overlay.source_weight_row_count,
        "normalised_weight_sum_min": float(overlay.weight_sums().min()),
        "normalised_weight_sum_max": float(overlay.weight_sums().max()),
        "nearest_cell_fallback_count": 0,
        "compiled_condition_count": len(prescription.conditions),
        "evaluated_condition_count": sum(
            condition.operational_status != "unmapped" for condition in prescription.conditions
        ),
        "unresolved_value_count": len(prescription.unresolved),
        "vicclim6_file_count": inventory["file_count"],
        "vicclim6_total_bytes": inventory["total_bytes"],
    }
    expected = {
        "data_sha256": args.data_sha256,
        "rule_sha256": args.expected_rule_sha256,
        "spatial_sha256": args.expected_spatial_sha256,
    }
    mismatches = {
        name: {"expected": value, "actual": result[name]}
        for name, value in expected.items()
        if value and value != result[name]
    }
    if mismatches:
        result["status"] = "failed"
        result["mismatches"] = mismatches
        write_json(args.output_dir / "quality_failure.json", result)
        raise ValueError(f"preflight SHA mismatch: {mismatches}")
    gates = {
        "all_176_burn_ids": len(overlay.burn_ids) == 176,
        "all_351_nonzero_weights": overlay.source_weight_row_count == 351,
        "normalised_weight_sums_within_1e-6": bool(
            np.allclose(overlay.weight_sums(), 1.0, atol=1e-6, rtol=0.0)
        ),
        "zero_nearest_cell_fallback": overlay.zero_coverage_burn_unit_count == 0,
        "complete_8_of_8_rule": len(prescription.conditions) == 8
        and not prescription.unresolved
        and all(
            condition.operational_status != "unmapped"
            for condition in prescription.conditions
        ),
        "expected_51_year_collection_file_count": inventory["file_count"] == 3672,
    }
    result["quality_gate"] = gates
    if not all(gates.values()):
        result["status"] = "failed"
        write_json(args.output_dir / "quality_failure.json", result)
        raise ValueError(f"preflight quality gate failed: {gates}")
    manifest = make_manifest(
        command=sys.argv,
        input_paths=[args.prescriptions, args.overlay],
        config={"data_sha256": args.data_sha256, "burn_class": args.burn_class},
        data_kind="real-metadata-preflight",
    )
    write_run_artifacts(args.output_dir, manifest=manifest, metrics=result)
    print(json.dumps(result, indent=2))
    return 0


def command_aggregate_burn_unit_climatology(args: argparse.Namespace) -> int:
    try:
        artifact = aggregate_annual_artifacts(
            args.input,
            expected_years=range(args.year_start, args.year_end + 1),
            expected_burn_unit_count=args.expected_burn_units,
        )
        validation = validate_compact_artifact(artifact)
        artifact["aggregation_git_sha"] = git_sha()
        write_json(args.output, artifact)
    except Exception as exc:
        write_json(
            args.failure_output,
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "git_sha": git_sha(),
                "hidden": False,
            },
        )
        raise
    print(json.dumps(validation, indent=2))
    return 0


def command_publish_burn_unit_climatology(args: argparse.Namespace) -> int:
    result = publish_compact_artifact(
        args.input,
        output_dir=args.output_dir,
        artifact_id=args.artifact_id,
    )
    write_json(args.output_dir / "publication_record.json", result)
    print(json.dumps(result, indent=2))
    return 0


def command_validate_burn_unit_climatology(args: argparse.Namespace) -> int:
    result = validate_compact_artifact(read_json(args.input))
    if args.output:
        write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


def command_smoke_burn_unit_service(args: argparse.Namespace) -> int:
    from fastapi.testclient import TestClient

    from .service import create_app

    catalog = BurnUnitClimatologyCatalog(args.artifact_catalog)
    artifact_id = args.artifact_id or catalog.artifact_ids[0]
    client = TestClient(create_app(artifact_catalog=str(args.artifact_catalog)))
    listed = client.get("/api/tools")
    if listed.status_code != 200:
        raise RuntimeError("tool discovery failed")
    response = client.post(
        "/api/tools/get_burn_unit_climatology:invoke",
        json={
            "arguments": {
                "artifact_id": artifact_id,
                "burn_ids": [args.burn_id] if args.burn_id else [],
                "year_start": args.year_start,
                "year_end": args.year_end,
            }
        },
    )
    body = response.json()
    if response.status_code != 200 or body.get("status") not in {"ok", "partial"}:
        raise RuntimeError(f"climatology tool smoke test failed: {body}")
    result = {
        "status": "passed",
        "artifact_id": artifact_id,
        "tool_listed": "get_burn_unit_climatology" in listed.json()["tools"],
        "query_status": body["status"],
        "query_record_count": body["result"]["record_count"],
        "artifact_sha256": body["result"]["artifact_sha256"],
        "provenance_status": body["provenance"]["status"],
        "read_only_precomputed": "no weather or rule recomputation"
        in " ".join(body["constraints"]),
        "git_sha": git_sha(),
    }
    if not result["tool_listed"] or not result["read_only_precomputed"]:
        raise RuntimeError(f"service smoke quality gate failed: {result}")
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    return 0


def _add_burn_unit_compute_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", type=Path, required=True, help="restricted VicClim6 root")
    parser.add_argument("--prescriptions", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--year", type=int, required=True, choices=range(1973, 2024))
    parser.add_argument("--burn-class", required=True)
    parser.add_argument("--data-sha256", required=True)
    parser.add_argument("--expected-rule-sha256")
    parser.add_argument("--expected-spatial-sha256")
    parser.add_argument("--expected-burn-units", type=int, default=176)
    parser.add_argument("--expected-weight-rows", type=int, default=351)
    parser.add_argument("--chunks", default='{"time":168,"latitude":37,"longitude":61}')
    parser.add_argument("--scheduler", choices=["synchronous", "threads"], default="synchronous")
    parser.add_argument("--dask-workers", type=int, default=1)
    parser.add_argument("--wind-reduction-factor", type=float, default=0.33)
    parser.add_argument("--fmc-rain-guard-mm", type=float, default=0.2)


def command_serve_tools(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is unavailable; install the 'serve' extra") from exc
    from .service import create_app

    uvicorn.run(
        create_app(
            artifact_catalog=(str(args.artifact_catalog) if args.artifact_catalog else None)
        ),
        host=args.host,
        port=args.port,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="burn-window")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser(
        "inspect", help="validate prescriptions and optional climate data"
    )
    inspect_parser.add_argument("--prescriptions", type=Path, required=True)
    inspect_parser.add_argument("--input", type=str)
    inspect_parser.add_argument(
        "--backend", choices=["netcdf", "zarr", "kerchunk"], default="netcdf"
    )
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
    analyse.add_argument(
        "--scheduler",
        choices=["synchronous", "threads"],
        default="threads",
    )
    analyse.add_argument("--dask-workers", type=int)
    analyse.add_argument("--durations", nargs="+", type=int, default=[2, 4, 6])
    analyse.add_argument(
        "--missing-policy", choices=[item.value for item in MissingPolicy], default="error"
    )
    analyse.add_argument("--include-unmapped", action="store_true")
    analyse.add_argument(
        "--derive-fuel-proxies",
        action="store_true",
        help=(
            "derive dry-fuel FMC and fuel-level wind proxies; records model provenance and "
            "does not convert the result into an operational approval"
        ),
    )
    analyse.add_argument("--wind-reduction-factor", type=float, default=0.33)
    analyse.add_argument("--fmc-rain-guard-mm", type=float, default=0.2)
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
    analyse.add_argument(
        "--region-geojson",
        type=Path,
        help="single-feature EPSG:4326 Polygon/MultiPolygon used to select grid-cell centres",
    )
    analyse.add_argument(
        "--region-label",
        help="human-readable region label recorded with the spatial evidence scope",
    )
    analyse.add_argument(
        "--threshold-scenarios",
        type=Path,
        help=(
            "JSON object mapping scenario names to workbook-field absolute deltas; "
            "positive widens and negative narrows each declared-unit interval"
        ),
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

    benchmark = subparsers.add_parser(
        "benchmark", help="compare NumPy and Dask on fixed synthetic data"
    )
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

    outcomes = subparsers.add_parser(
        "official-outcomes",
        help="align official JFMP planned-burn units with FFMVic Fire History outcomes",
    )
    outcomes.add_argument("--planned-district", default="Murray Goldfields")
    outcomes.add_argument("--history-district", default="Loddon Mallee - Murray Goldfields")
    outcomes.add_argument("--output-dir", type=Path, required=True)
    outcomes.set_defaults(handler=command_official_outcomes)

    overlay = subparsers.add_parser(
        "build-burn-unit-overlay",
        help="build official burn-unit to VicClim6 area-weighted grid contracts",
    )
    overlay.add_argument("--grid", type=Path, required=True)
    overlay.add_argument("--geojson", type=Path)
    overlay.add_argument("--where", default="1=1")
    overlay.add_argument("--id-property", default="TREAT_NO")
    overlay.add_argument("--latitude-name", default="latitude")
    overlay.add_argument("--longitude-name", default="longitude")
    overlay.add_argument("--output-dir", type=Path, required=True)
    overlay.set_defaults(handler=command_burn_unit_overlay)

    preflight = subparsers.add_parser(
        "burn-unit-climatology-preflight",
        help="validate the restricted data, complete rule and sparse overlay contracts",
    )
    preflight.add_argument("--input", type=Path, required=True)
    preflight.add_argument("--prescriptions", type=Path, required=True)
    preflight.add_argument("--overlay", type=Path, required=True)
    preflight.add_argument("--burn-class", required=True)
    preflight.add_argument("--data-sha256", required=True)
    preflight.add_argument("--expected-rule-sha256", required=True)
    preflight.add_argument("--expected-spatial-sha256", required=True)
    preflight.add_argument("--expected-burn-units", type=int, default=176)
    preflight.add_argument("--expected-weight-rows", type=int, default=351)
    preflight.add_argument("--output-dir", type=Path, required=True)
    preflight.set_defaults(handler=command_burn_unit_preflight)

    burn_year = subparsers.add_parser(
        "burn-unit-climatology-year",
        help="evaluate one year at sparse overlay cells and write 176 burn-ID records",
    )
    _add_burn_unit_compute_arguments(burn_year)
    burn_year.add_argument("--output-dir", type=Path, required=True)
    burn_year.set_defaults(handler=command_burn_unit_year)

    compare_burn_year = subparsers.add_parser(
        "compare-burn-unit-climatology-year",
        help="directly recompute and compare one annual sparse pilot",
    )
    _add_burn_unit_compute_arguments(compare_burn_year)
    compare_burn_year.add_argument("--pilot-dir", type=Path, required=True)
    compare_burn_year.add_argument("--output-dir", type=Path, required=True)
    compare_burn_year.set_defaults(handler=command_compare_burn_unit_year)

    aggregate_burn = subparsers.add_parser(
        "aggregate-burn-unit-climatology",
        help="quality-gate annual burn-ID artifacts and build the compact query artifact",
    )
    aggregate_burn.add_argument("--input", type=Path, required=True)
    aggregate_burn.add_argument("--year-start", type=int, default=1973)
    aggregate_burn.add_argument("--year-end", type=int, default=2023)
    aggregate_burn.add_argument("--expected-burn-units", type=int, default=176)
    aggregate_burn.add_argument("--output", type=Path, required=True)
    aggregate_burn.add_argument("--failure-output", type=Path, required=True)
    aggregate_burn.set_defaults(handler=command_aggregate_burn_unit_climatology)

    publish_burn = subparsers.add_parser(
        "publish-burn-unit-climatology",
        help="validate and publish an allowlisted compact artifact and catalog",
    )
    publish_burn.add_argument("--input", type=Path, required=True)
    publish_burn.add_argument("--output-dir", type=Path, required=True)
    publish_burn.add_argument("--artifact-id", required=True)
    publish_burn.set_defaults(handler=command_publish_burn_unit_climatology)

    validate_burn = subparsers.add_parser(
        "validate-burn-unit-climatology",
        help="validate a compact burn-ID artifact schema and quality gates",
    )
    validate_burn.add_argument("--input", type=Path, required=True)
    validate_burn.add_argument("--output", type=Path)
    validate_burn.set_defaults(handler=command_validate_burn_unit_climatology)

    smoke_burn = subparsers.add_parser(
        "smoke-burn-unit-service",
        help="invoke the read-only climatology tool against a precomputed artifact catalog",
    )
    smoke_burn.add_argument("--artifact-catalog", type=Path, required=True)
    smoke_burn.add_argument("--artifact-id")
    smoke_burn.add_argument("--burn-id")
    smoke_burn.add_argument("--year-start", type=int, default=1973)
    smoke_burn.add_argument("--year-end", type=int, default=2023)
    smoke_burn.add_argument("--output", type=Path, required=True)
    smoke_burn.set_defaults(handler=command_smoke_burn_unit_service)

    serve = subparsers.add_parser("serve-tools", help="serve the typed trusted-tool registry")
    serve.add_argument("--artifact-catalog", type=Path)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.set_defaults(handler=command_serve_tools)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (FileNotFoundError, KeyError, TypeError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
