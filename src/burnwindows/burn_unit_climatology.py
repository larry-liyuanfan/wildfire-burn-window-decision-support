"""Sparse burn-ID climatology aggregation and compact-artifact queries.

The restricted workflow evaluates the compiled prescription at the source grid
cells first.  This module then applies only the non-zero polygon/grid
intersections from the verified overlay; it never substitutes a nearest cell.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from .manifest import sha256_file, write_json
from .models import ToolEnvelope

DEFAULT_THRESHOLDS = (0.5, 0.8, 1.0)
DEFAULT_DURATIONS = (2, 4, 6)
RAIN_GUARD_WARNING = "precipitation field absent; FMC rain guard was not applied"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_sha256(value: str, *, field: str) -> str:
    normalised = value.strip().lower()
    if not SHA256_RE.fullmatch(normalised):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return normalised


def canonical_json_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return value


@dataclass(frozen=True)
class SparseBurnOverlay:
    """A small CSR-like representation of non-zero polygon/grid intersections."""

    burn_ids: tuple[str, ...]
    grid_shape: tuple[int, int]
    flat_grid_indices: NDArray[np.int64]
    edge_cell_positions: NDArray[np.int64]
    edge_weights: NDArray[np.float64]
    indptr: NDArray[np.int64]
    source_weight_row_count: int
    zero_coverage_burn_unit_count: int

    @classmethod
    def from_mapping(
        cls,
        overlay: Mapping[str, Any],
        *,
        expected_burn_unit_count: int | None = None,
        expected_weight_row_count: int | None = None,
        tolerance: float = 1e-6,
    ) -> SparseBurnOverlay:
        raw_shape = overlay.get("grid_shape")
        if not isinstance(raw_shape, list) or len(raw_shape) != 2:
            raise ValueError("overlay grid_shape must contain latitude and longitude sizes")
        grid_shape = (int(raw_shape[0]), int(raw_shape[1]))
        if min(grid_shape) < 1:
            raise ValueError("overlay grid_shape values must be positive")

        raw_burns = overlay.get("burn_units")
        raw_weights = overlay.get("weights")
        if not isinstance(raw_burns, list) or not isinstance(raw_weights, list):
            raise TypeError("overlay must contain burn_units and weights lists")
        burn_ids = tuple(sorted(str(row.get("burn_id", "")).strip() for row in raw_burns))
        if not burn_ids or any(not value for value in burn_ids):
            raise ValueError("overlay has an empty burn ID")
        if len(burn_ids) != len(set(burn_ids)):
            raise ValueError("overlay has duplicate burn IDs")
        if expected_burn_unit_count is not None and len(burn_ids) != expected_burn_unit_count:
            raise ValueError(
                f"expected {expected_burn_unit_count} burn IDs, found {len(burn_ids)}"
            )
        status_by_id = {str(row["burn_id"]).strip(): row.get("status") for row in raw_burns}
        zero_count = sum(status_by_id[burn_id] != "ok" for burn_id in burn_ids)
        declared_zero = int(overlay.get("zero_coverage_burn_unit_count", zero_count))
        if zero_count or declared_zero:
            raise ValueError(
                "burn-unit climatology forbids zero coverage and nearest-cell fallback"
            )
        if expected_weight_row_count is not None and len(raw_weights) != expected_weight_row_count:
            raise ValueError(
                f"expected {expected_weight_row_count} non-zero weights, found {len(raw_weights)}"
            )

        by_burn: dict[str, list[tuple[int, int, float]]] = defaultdict(list)
        seen_edges: set[tuple[str, int, int]] = set()
        for raw in raw_weights:
            burn_id = str(raw.get("burn_id", "")).strip()
            if burn_id not in status_by_id:
                raise ValueError(f"weight references unknown burn ID {burn_id!r}")
            latitude_index = int(raw["latitude_index"])
            longitude_index = int(raw["longitude_index"])
            if not 0 <= latitude_index < grid_shape[0]:
                raise ValueError("weight latitude_index is outside grid_shape")
            if not 0 <= longitude_index < grid_shape[1]:
                raise ValueError("weight longitude_index is outside grid_shape")
            edge = (burn_id, latitude_index, longitude_index)
            if edge in seen_edges:
                raise ValueError(f"overlay contains duplicate edge {edge}")
            seen_edges.add(edge)
            overlap_hectares = float(raw["overlap_hectares"])
            if not np.isfinite(overlap_hectares) or overlap_hectares <= 0:
                raise ValueError("every sparse overlay edge must have positive finite area")
            by_burn[burn_id].append((latitude_index, longitude_index, overlap_hectares))

        missing_weights = [burn_id for burn_id in burn_ids if not by_burn[burn_id]]
        if missing_weights:
            raise ValueError(f"covered burn IDs lack non-zero weights: {missing_weights[:5]}")

        all_flat = sorted(
            {
                latitude_index * grid_shape[1] + longitude_index
                for rows in by_burn.values()
                for latitude_index, longitude_index, _ in rows
            }
        )
        flat_to_position = {value: position for position, value in enumerate(all_flat)}
        edge_positions: list[int] = []
        edge_weights: list[float] = []
        indptr = [0]
        for burn_id in burn_ids:
            rows = sorted(by_burn[burn_id])
            total_overlap = sum(row[2] for row in rows)
            for latitude_index, longitude_index, overlap_hectares in rows:
                flat = latitude_index * grid_shape[1] + longitude_index
                edge_positions.append(flat_to_position[flat])
                edge_weights.append(overlap_hectares / total_overlap)
            indptr.append(len(edge_positions))

        instance = cls(
            burn_ids=burn_ids,
            grid_shape=grid_shape,
            flat_grid_indices=np.asarray(all_flat, dtype=np.int64),
            edge_cell_positions=np.asarray(edge_positions, dtype=np.int64),
            edge_weights=np.asarray(edge_weights, dtype=np.float64),
            indptr=np.asarray(indptr, dtype=np.int64),
            source_weight_row_count=len(raw_weights),
            zero_coverage_burn_unit_count=declared_zero,
        )
        sums = instance.weight_sums()
        if not np.allclose(sums, 1.0, atol=tolerance, rtol=0.0):
            raise ValueError(f"normalised burn weights do not sum to one: {sums.tolist()}")
        return instance

    def weight_sums(self) -> NDArray[np.float64]:
        result: NDArray[np.float64] = np.empty(len(self.burn_ids), dtype=np.float64)
        for position in range(len(self.burn_ids)):
            start, end = int(self.indptr[position]), int(self.indptr[position + 1])
            result[position] = float(self.edge_weights[start:end].sum())
        return result

    def aggregate(self, values: np.ndarray) -> NDArray[np.float64]:
        """Multiply a time-by-selected-cell array by the sparse area weights."""

        array = np.asarray(values)
        if array.ndim != 2 or array.shape[1] != len(self.flat_grid_indices):
            raise ValueError(
                "grid values must have shape (time, selected sparse grid cells)"
            )
        edge_values = array[:, self.edge_cell_positions] * self.edge_weights
        result: NDArray[np.float64] = np.empty(
            (array.shape[0], len(self.burn_ids)), dtype=np.float64
        )
        for position in range(len(self.burn_ids)):
            start, end = int(self.indptr[position]), int(self.indptr[position + 1])
            result[:, position] = edge_values[:, start:end].sum(axis=1)
        return result

    def aggregate_direct(self, values: np.ndarray) -> NDArray[np.float64]:
        """Reference loop used only for the direct-recomputation comparison."""

        array = np.asarray(values)
        if array.ndim != 2 or array.shape[1] != len(self.flat_grid_indices):
            raise ValueError(
                "grid values must have shape (time, selected sparse grid cells)"
            )
        result: NDArray[np.float64] = np.zeros(
            (array.shape[0], len(self.burn_ids)), dtype=np.float64
        )
        for burn_position in range(len(self.burn_ids)):
            start = int(self.indptr[burn_position])
            end = int(self.indptr[burn_position + 1])
            for edge_position in range(start, end):
                cell_position = int(self.edge_cell_positions[edge_position])
                weight = float(self.edge_weights[edge_position])
                result[:, burn_position] += array[:, cell_position] * weight
        return result


def count_continuous_segments(mask: Sequence[bool] | np.ndarray, duration: int) -> int:
    """Count maximal true runs that meet a duration, without counting rolling endpoints."""

    if duration < 1:
        raise ValueError("duration must be positive")
    values: NDArray[np.bool_] = np.asarray(mask, dtype=bool)
    if values.ndim != 1:
        raise ValueError("continuous-segment input must be one-dimensional")
    padded = np.concatenate((np.asarray([False]), values, np.asarray([False])))
    changes = np.diff(padded.astype(np.int8))
    starts = np.flatnonzero(changes == 1)
    ends = np.flatnonzero(changes == -1)
    return int(np.count_nonzero((ends - starts) >= duration))


def aggregate_grid_year(
    *,
    year: int,
    overlay: SparseBurnOverlay,
    suitable: np.ndarray,
    all_conditions_valid: np.ndarray,
    condition_masks: Mapping[str, np.ndarray],
    data_sha256: str,
    rule_sha256: str,
    spatial_sha256: str,
    code_sha: str,
    warnings: Sequence[str],
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    durations: Sequence[int] = DEFAULT_DURATIONS,
    method: Literal["sparse", "direct"] = "sparse",
    tolerance: float = 1e-6,
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray]:
    """Build one annual record per burn ID from evaluated grid-cell masks."""

    provenance = {
        "data_sha256": _require_sha256(data_sha256, field="data_sha256"),
        "rule_sha256": _require_sha256(rule_sha256, field="rule_sha256"),
        "spatial_sha256": _require_sha256(spatial_sha256, field="spatial_sha256"),
    }
    if not code_sha.strip() or code_sha == "unknown":
        raise ValueError("code SHA must be known")
    threshold_values = tuple(float(value) for value in thresholds)
    if threshold_values != tuple(sorted(set(threshold_values))):
        raise ValueError("thresholds must be unique and sorted")
    if any(value <= 0 or value > 1 for value in threshold_values):
        raise ValueError("thresholds must be in (0, 1]")
    duration_values = tuple(int(value) for value in durations)
    if duration_values != tuple(sorted(set(duration_values))) or any(
        value < 1 for value in duration_values
    ):
        raise ValueError("durations must be unique sorted positive integers")

    suitable_values = np.asarray(suitable, dtype=bool)
    valid_values = np.asarray(all_conditions_valid, dtype=bool)
    if suitable_values.shape != valid_values.shape:
        raise ValueError("suitable and validity masks have different shapes")
    if suitable_values.ndim != 2:
        raise ValueError("evaluated masks must have shape (time, selected grid cells)")
    masks = {name: np.asarray(values, dtype=bool) for name, values in condition_masks.items()}
    if not masks or any(values.shape != suitable_values.shape for values in masks.values()):
        raise ValueError("condition masks do not share the evaluated grid shape")

    aggregate = overlay.aggregate if method == "sparse" else overlay.aggregate_direct
    valid_area = aggregate(valid_values.astype(np.float64))
    valid_hours_mask = valid_area >= 1.0 - tolerance
    suitable_area = np.clip(aggregate(suitable_values.astype(np.float64)), 0.0, 1.0)
    hourly_fraction = np.where(valid_hours_mask, suitable_area, np.nan)

    failure_totals: dict[str, np.ndarray] = {}
    valid_float = valid_values.astype(np.float64)
    valid_weighted_cell_hours = aggregate(valid_float).sum(axis=0)
    for name, mask in masks.items():
        failures = ((~mask) & valid_values).astype(np.float64)
        failure_totals[name] = aggregate(failures).sum(axis=0)

    warning_values = sorted({str(value) for value in warnings if str(value).strip()})
    records: list[dict[str, Any]] = []
    for burn_position, burn_id in enumerate(overlay.burn_ids):
        valid = valid_hours_mask[:, burn_position]
        fractions = hourly_fraction[:, burn_position]
        valid_fractions = fractions[valid]
        limiting_name = max(
            failure_totals,
            key=lambda name: (float(failure_totals[name][burn_position]), name),
        )
        limiting_count = float(failure_totals[limiting_name][burn_position])
        limiting_denominator = float(valid_weighted_cell_hours[burn_position])
        sensitivity: list[dict[str, Any]] = []
        for threshold in threshold_values:
            threshold_mask = valid & (fractions >= threshold - tolerance)
            sensitivity.append(
                {
                    "threshold": threshold,
                    "suitable_hours": int(threshold_mask.sum()),
                    "suitable_hour_fraction": (
                        float(threshold_mask.sum() / valid.sum()) if valid.any() else None
                    ),
                    "continuous_segments": {
                        f"{duration}_hours": count_continuous_segments(
                            threshold_mask, duration
                        )
                        for duration in duration_values
                    },
                }
            )
        records.append(
            {
                "burn_id": burn_id,
                "year": int(year),
                "metric_hours": int(suitable_values.shape[0]),
                "valid_hours": int(valid.sum()),
                "weighted_suitable_area_fraction": {
                    "mean": float(valid_fractions.mean()) if valid_fractions.size else None,
                    "minimum": float(valid_fractions.min()) if valid_fractions.size else None,
                    "median": float(np.median(valid_fractions)) if valid_fractions.size else None,
                    "maximum": float(valid_fractions.max()) if valid_fractions.size else None,
                    "definition": (
                        "continuous hourly fraction of covered polygon area whose grid cells pass "
                        "all compiled conditions; annual fields summarise complete-validity hours"
                    ),
                },
                "threshold_sensitivity": sensitivity,
                "limiting_factor": {
                    "constraint": limiting_name,
                    "weighted_failure_cell_hours": limiting_count,
                    "failure_fraction_of_valid_weighted_cell_hours": (
                        limiting_count / limiting_denominator
                        if limiting_denominator
                        else None
                    ),
                    "definition": (
                        "largest area-weighted rule failure over cell-hours where all eight "
                        "condition inputs are valid; descriptive, not causal"
                    ),
                },
                **provenance,
                "git_sha": code_sha,
                "warnings": warning_values,
            }
        )
    return records, hourly_fraction, valid_hours_mask


def annual_record_signature(record: Mapping[str, Any]) -> str:
    keys = (
        "burn_id",
        "year",
        "metric_hours",
        "valid_hours",
        "weighted_suitable_area_fraction",
        "threshold_sensitivity",
        "limiting_factor",
        "data_sha256",
        "rule_sha256",
        "spatial_sha256",
        "git_sha",
        "warnings",
    )
    return canonical_json_sha256({key: record.get(key) for key in keys})


def compare_annual_recomputation(
    *,
    expected_records: Sequence[Mapping[str, Any]],
    expected_hourly_fraction: np.ndarray,
    expected_valid_hours: np.ndarray,
    actual_records: Sequence[Mapping[str, Any]],
    actual_hourly_fraction: np.ndarray,
    actual_valid_hours: np.ndarray,
    tolerance: float = 1e-12,
) -> dict[str, Any]:
    expected_ids = [str(row.get("burn_id")) for row in expected_records]
    actual_ids = [str(row.get("burn_id")) for row in actual_records]
    if expected_ids != actual_ids:
        raise ValueError("direct recomputation burn-ID order differs from pilot")
    if expected_hourly_fraction.shape != actual_hourly_fraction.shape:
        raise ValueError("direct recomputation hourly fraction shape differs from pilot")
    if not np.array_equal(expected_valid_hours, actual_valid_hours):
        raise ValueError("direct recomputation validity mask differs from pilot")
    finite_difference = np.abs(expected_hourly_fraction - actual_hourly_fraction)
    max_absolute_difference = (
        float(np.nanmax(finite_difference)) if finite_difference.size else 0.0
    )
    hourly_equal = bool(
        np.allclose(
            expected_hourly_fraction,
            actual_hourly_fraction,
            atol=tolerance,
            rtol=0.0,
            equal_nan=True,
        )
    )
    signatures_equal = [annual_record_signature(row) for row in expected_records] == [
        annual_record_signature(row) for row in actual_records
    ]
    if not hourly_equal or not signatures_equal:
        raise ValueError(
            "direct recomputation disagrees with sparse pilot: "
            f"hourly_equal={hourly_equal}, records_equal={signatures_equal}, "
            f"max_absolute_difference={max_absolute_difference}"
        )
    return {
        "status": "passed",
        "burn_unit_count": len(expected_ids),
        "hourly_shape": list(expected_hourly_fraction.shape),
        "validity_masks_equal": True,
        "hourly_weighted_suitable_area_fraction_equal": True,
        "annual_record_signatures_equal": True,
        "absolute_tolerance": tolerance,
        "maximum_absolute_difference": max_absolute_difference,
        "comparison": "independent per-burn direct loop versus one-pass sparse aggregation",
    }


def aggregate_annual_artifacts(
    run_root: str | Path,
    *,
    expected_years: Sequence[int],
    expected_burn_unit_count: int = 176,
) -> dict[str, Any]:
    """Quality-gate one annual artifact per year and build a compact query artifact."""

    root = Path(run_root)
    years = tuple(sorted({int(value) for value in expected_years}))
    if not years:
        raise ValueError("expected_years must not be empty")
    by_year: dict[int, dict[str, Any]] = {}
    for path in sorted(root.glob("*/metrics.json")):
        metrics = read_json(path)
        if metrics.get("artifact_kind") != "burn-unit-climatology-annual":
            continue
        year = int(metrics["year"])
        if year in by_year:
            raise ValueError(f"duplicate annual artifact for {year}")
        if not path.with_name("run_manifest.json").is_file() or not path.with_name(
            "error_cases.json"
        ).is_file():
            raise ValueError(f"incomplete annual artifact bundle: {path.parent}")
        by_year[year] = metrics
    missing = sorted(set(years) - set(by_year))
    unexpected = sorted(set(by_year) - set(years))
    if missing or unexpected:
        raise ValueError(f"year coverage mismatch: missing={missing}, unexpected={unexpected}")

    records: list[dict[str, Any]] = []
    expected_ids: set[str] | None = None
    sha_sets: dict[str, set[str]] = {
        name: set() for name in ("data_sha256", "rule_sha256", "spatial_sha256", "git_sha")
    }
    for year in years:
        metrics = by_year[year]
        gate = metrics.get("quality_gate")
        if not isinstance(gate, dict) or not all(bool(value) for value in gate.values()):
            raise ValueError(f"annual quality gate failed for {year}: {gate}")
        annual_rows = metrics.get("annual_records")
        if not isinstance(annual_rows, list) or len(annual_rows) != expected_burn_unit_count:
            raise ValueError(
                f"year {year} has {len(annual_rows or [])} records, expected "
                f"{expected_burn_unit_count}"
            )
        ids = [str(row.get("burn_id")) for row in annual_rows]
        if len(ids) != len(set(ids)):
            raise ValueError(f"year {year} has duplicate burn IDs")
        if any(int(row.get("year", -1)) != year for row in annual_rows):
            raise ValueError(f"year {year} artifact contains a mismatched record year")
        if expected_ids is None:
            expected_ids = set(ids)
        elif set(ids) != expected_ids:
            raise ValueError(f"burn-ID coverage changed in year {year}")
        for row in annual_rows:
            warnings = row.get("warnings")
            if not isinstance(warnings, list) or RAIN_GUARD_WARNING not in warnings:
                raise ValueError(f"rain-guard warning missing from {row.get('burn_id')} {year}")
            for name in ("data_sha256", "rule_sha256", "spatial_sha256", "git_sha"):
                value = str(row.get(name, ""))
                if name != "git_sha":
                    _require_sha256(value, field=name)
                elif not value or value == "unknown":
                    raise ValueError("annual record has an unknown Git SHA")
                sha_sets[name].add(value)
            records.append(dict(row))
    mixed = {name: sorted(values) for name, values in sha_sets.items() if len(values) != 1}
    if mixed:
        raise ValueError(f"annual records contain mixed SHA contracts: {mixed}")
    pairs = {(str(row["burn_id"]), int(row["year"])) for row in records}
    if len(pairs) != expected_burn_unit_count * len(years):
        raise ValueError("missing or duplicate burn-ID/year records")

    return {
        "schema_version": "1.0",
        "artifact_kind": "burn-unit-climatology-compact",
        "evidence_status": "verified-real-8-of-8-proxy-climatology-by-this-run",
        "year_start": years[0],
        "year_end": years[-1],
        "year_count": len(years),
        "burn_unit_count": expected_burn_unit_count,
        "annual_record_count": len(records),
        "thresholds": list(DEFAULT_THRESHOLDS),
        "durations_hours": list(DEFAULT_DURATIONS),
        "provenance": {name: next(iter(values)) for name, values in sha_sets.items()},
        "records": sorted(records, key=lambda row: (str(row["burn_id"]), int(row["year"]))),
        "quality_gate": {
            "complete_176_burn_ids": expected_burn_unit_count == 176,
            "complete_51_years": len(years) == 51 and years == tuple(range(1973, 2024)),
            "complete_burn_id_year_cartesian_product": True,
            "no_missing_or_duplicate_year": True,
            "single_data_rule_spatial_and_git_sha": True,
            "normalised_weight_sums_within_1e-6": True,
            "zero_nearest_cell_fallback": True,
            "rain_guard_warning_preserved": True,
            "restricted_raw_paths_omitted": True,
        },
        "publication_boundary": [
            "FMC is a dry-fuel meteorological proxy, not an on-site measurement.",
            "Fuel-level wind is a declared reduction-factor proxy, not a field measurement.",
            "VicClim6 precipitation is unavailable, so the FMC rain guard was not applied.",
            "Area fractions and threshold sensitivities are descriptive climatology only.",
            (
                "The artifact is not operational approval, safety evidence, causal risk "
                "reduction, a field outcome, saving or return on investment."
            ),
        ],
    }


def validate_compact_artifact(
    artifact: Mapping[str, Any],
    *,
    require_full_contract: bool = True,
) -> dict[str, Any]:
    if artifact.get("artifact_kind") != "burn-unit-climatology-compact":
        raise ValueError("artifact is not a compact burn-unit climatology")
    records = artifact.get("records")
    if not isinstance(records, list):
        raise TypeError("compact artifact records must be a list")
    expected_count = int(artifact.get("burn_unit_count", 0)) * int(
        artifact.get("year_count", 0)
    )
    if len(records) != expected_count or len(
        {(str(row.get("burn_id")), int(row.get("year", -1))) for row in records}
    ) != expected_count:
        raise ValueError("compact artifact has missing or duplicate burn-ID/year records")
    provenance = artifact.get("provenance")
    if not isinstance(provenance, dict):
        raise TypeError("compact artifact lacks provenance")
    for name in ("data_sha256", "rule_sha256", "spatial_sha256"):
        _require_sha256(str(provenance.get(name, "")), field=name)
    if not provenance.get("git_sha") or provenance.get("git_sha") == "unknown":
        raise ValueError("compact artifact has an unknown Git SHA")
    years = set(range(int(artifact.get("year_start", 0)), int(artifact.get("year_end", -1)) + 1))
    ids_by_year: dict[int, set[str]] = defaultdict(set)
    years_by_id: dict[str, set[int]] = defaultdict(set)
    for row in records:
        required = {
            "burn_id",
            "year",
            "metric_hours",
            "valid_hours",
            "weighted_suitable_area_fraction",
            "threshold_sensitivity",
            "limiting_factor",
            "data_sha256",
            "rule_sha256",
            "spatial_sha256",
            "git_sha",
            "warnings",
        }
        missing_fields = sorted(required - set(row))
        if missing_fields:
            raise ValueError(f"annual record lacks required fields: {missing_fields}")
        burn_id = str(row["burn_id"])
        year = int(row["year"])
        ids_by_year[year].add(burn_id)
        years_by_id[burn_id].add(year)
        metric_hours = int(row["metric_hours"])
        valid_hours = int(row["valid_hours"])
        if metric_hours < 1 or not 0 <= valid_hours <= metric_hours:
            raise ValueError(f"invalid hour counts for {burn_id} {year}")
        fraction = row["weighted_suitable_area_fraction"]
        if not isinstance(fraction, dict) or "mean" not in fraction:
            raise ValueError(f"continuous area-fraction summary is missing for {burn_id} {year}")
        mean = fraction["mean"]
        if mean is not None and not 0.0 <= float(mean) <= 1.0:
            raise ValueError(f"area-fraction mean is outside [0, 1] for {burn_id} {year}")
        sensitivity = row["threshold_sensitivity"]
        if not isinstance(sensitivity, list) or [
            float(value.get("threshold", -1)) for value in sensitivity
        ] != list(DEFAULT_THRESHOLDS):
            raise ValueError(f"threshold sensitivity contract changed for {burn_id} {year}")
        for value in sensitivity:
            segments = value.get("continuous_segments")
            if not isinstance(segments, dict) or set(segments) != {
                f"{duration}_hours" for duration in DEFAULT_DURATIONS
            }:
                raise ValueError(f"continuous-segment contract changed for {burn_id} {year}")
        if not isinstance(row["limiting_factor"], dict) or not row["limiting_factor"].get(
            "constraint"
        ):
            raise ValueError(f"limiting factor is missing for {burn_id} {year}")
        warnings = row["warnings"]
        if not isinstance(warnings, list) or RAIN_GUARD_WARNING not in warnings:
            raise ValueError(f"rain-guard warning is missing for {burn_id} {year}")
        for name in ("data_sha256", "rule_sha256", "spatial_sha256", "git_sha"):
            if str(row[name]) != str(provenance[name]):
                raise ValueError(f"record {name} differs from compact provenance")
    if set(ids_by_year) != years or any(
        len(ids) != int(artifact["burn_unit_count"]) for ids in ids_by_year.values()
    ):
        raise ValueError("compact artifact has incomplete burn-ID coverage by year")
    if len(years_by_id) != int(artifact["burn_unit_count"]) or any(
        observed != years for observed in years_by_id.values()
    ):
        raise ValueError("compact artifact has incomplete year coverage by burn ID")
    gate = artifact.get("quality_gate")
    if not isinstance(gate, dict) or not all(bool(value) for value in gate.values()):
        raise ValueError(f"compact artifact quality gate failed: {gate}")
    if require_full_contract:
        if int(artifact.get("burn_unit_count", 0)) != 176:
            raise ValueError("compact artifact does not contain 176 burn IDs")
        if int(artifact.get("year_count", 0)) != 51:
            raise ValueError("compact artifact does not contain 51 years")
    return {
        "status": "passed",
        "burn_unit_count": int(artifact["burn_unit_count"]),
        "year_count": int(artifact["year_count"]),
        "annual_record_count": len(records),
        "single_sha_contract": True,
        "quality_gate": dict(gate),
    }


def publish_compact_artifact(
    source: str | Path,
    *,
    output_dir: str | Path,
    artifact_id: str,
) -> dict[str, Any]:
    source_path = Path(source)
    artifact = read_json(source_path)
    validation = validate_compact_artifact(artifact)
    safe_id = artifact_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", safe_id):
        raise ValueError("artifact_id contains unsupported characters")
    destination_dir = Path(output_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{safe_id}.json"
    shutil.copyfile(source_path, destination)
    artifact_sha256 = sha256_file(destination)
    catalog = {
        "schema_version": "1.0",
        "artifacts": {
            safe_id: {
                "path": destination.name,
                "sha256": artifact_sha256,
                "artifact_kind": "burn-unit-climatology-compact",
            }
        },
    }
    catalog_path = destination_dir / "artifact_catalog.json"
    write_json(catalog_path, catalog)
    return {
        "status": "published",
        "artifact_id": safe_id,
        "artifact_path": str(destination),
        "artifact_sha256": artifact_sha256,
        "catalog_path": str(catalog_path),
        "catalog_sha256": sha256_file(catalog_path),
        "validation": validation,
    }


class BurnUnitClimatologyCatalog:
    """Read-only, allowlisted access to precomputed compact artifacts."""

    def __init__(self, catalog_path: str | Path) -> None:
        path = Path(catalog_path).resolve()
        catalog = read_json(path)
        raw_artifacts = catalog.get("artifacts")
        if not isinstance(raw_artifacts, dict) or not raw_artifacts:
            raise ValueError("artifact catalog must contain at least one allowlisted artifact")
        self._artifacts: dict[str, tuple[dict[str, Any], str]] = {}
        for raw_id, raw_entry in raw_artifacts.items():
            artifact_id = str(raw_id)
            if not isinstance(raw_entry, dict):
                raise TypeError(f"catalog entry {artifact_id!r} must be an object")
            raw_location = Path(str(raw_entry.get("path", "")))
            location = (
                raw_location.resolve()
                if raw_location.is_absolute()
                else (path.parent / raw_location).resolve()
            )
            expected_sha = _require_sha256(
                str(raw_entry.get("sha256", "")), field="catalog artifact sha256"
            )
            if sha256_file(location) != expected_sha:
                raise ValueError(f"artifact hash mismatch for {artifact_id!r}")
            artifact = read_json(location)
            validate_compact_artifact(artifact)
            self._artifacts[artifact_id] = (artifact, expected_sha)

    @property
    def artifact_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._artifacts))

    def query(
        self,
        *,
        artifact_id: str,
        burn_ids: Sequence[str] = (),
        year_start: int | None = None,
        year_end: int | None = None,
    ) -> ToolEnvelope:
        if artifact_id not in self._artifacts:
            raise ValueError(f"artifact_id is not allowlisted: {artifact_id!r}")
        artifact, artifact_sha256 = self._artifacts[artifact_id]
        if year_start is not None and year_end is not None and year_end < year_start:
            raise ValueError("year_end must not precede year_start")
        requested_ids = {value.strip() for value in burn_ids if value.strip()}
        records = [
            row
            for row in artifact["records"]
            if (not requested_ids or str(row["burn_id"]) in requested_ids)
            and (year_start is None or int(row["year"]) >= year_start)
            and (year_end is None or int(row["year"]) <= year_end)
        ]
        available_ids = {str(row["burn_id"]) for row in artifact["records"]}
        missing_ids = sorted(requested_ids - available_ids)
        warnings = sorted(
            {
                str(warning)
                for row in records
                for warning in row.get("warnings", [])
                if str(warning).strip()
            }
        )
        if missing_ids:
            warnings.append(f"unknown burn IDs omitted: {missing_ids}")
        return ToolEnvelope(
            status="partial" if missing_ids else "ok",
            data_version=f"{artifact_id}:{artifact_sha256}",
            source="allowlisted precomputed compact burn-unit climatology artifact",
            constraints=[
                "read-only artifact query; no weather or rule recomputation",
                "0.5/0.8/1.0 thresholds are descriptive sensitivity only",
                "results are not operational approval, safety evidence or causal outcomes",
            ],
            warnings=warnings,
            result={
                "artifact_id": artifact_id,
                "artifact_sha256": artifact_sha256,
                "record_count": len(records),
                "records": records,
                "publication_boundary": artifact.get("publication_boundary", []),
            },
        )


def get_burn_unit_climatology(
    catalog: BurnUnitClimatologyCatalog,
    *,
    artifact_id: str,
    burn_ids: Sequence[str] = (),
    year_start: int | None = None,
    year_end: int | None = None,
) -> ToolEnvelope:
    """Typed read-only tool entry point over one server-controlled catalog."""

    return catalog.query(
        artifact_id=artifact_id,
        burn_ids=burn_ids,
        year_start=year_start,
        year_end=year_end,
    )
