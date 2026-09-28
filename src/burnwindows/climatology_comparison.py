"""Deterministic comparisons of precomputed annual values, not fire decisions."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from typing import Any

from .models import ToolEnvelope


def comparison_view(
    envelope: ToolEnvelope, *, threshold: float = 0.8, duration_hours: int = 4,
    reference_year: int | None = None, reference_burn_id: str | None = None,
) -> ToolEnvelope:
    if threshold not in (0.5, 0.8, 1.0) or duration_hours not in (2, 4, 6):
        raise ValueError("unsupported descriptive threshold/duration")
    if envelope.status != "ok" or not isinstance(envelope.result, dict):
        raise ValueError("comparison needs a verified query result")
    records = envelope.result["records"]
    if not records:
        raise ValueError("no covered records; cannot compare or substitute nearest unit")
    if len({(r["burn_id"], r["year"]) for r in records}) != len(records):
        raise ValueError("duplicate annual record")
    provenance = {key: {r[key] for r in records}
                  for key in ("data_sha256", "rule_sha256", "spatial_sha256", "git_sha")}
    if any(len(values) != 1 for values in provenance.values()):
        raise ValueError("mixed data/rule/spatial/code versions cannot be compared")
    table: list[dict[str, Any]] = []
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in sorted(records, key=lambda r: (r["burn_id"], r["year"])):
        valid, total = record["valid_hours"], record["metric_hours"]
        if not isinstance(valid, int) or not 0 <= valid <= total or total <= 0:
            raise ValueError("invalid annual coverage")
        mean = record["weighted_suitable_area_fraction"]["mean"]
        if (valid == 0) != (mean is None):
            raise ValueError("missing mean/valid-hour contract")
        if mean is not None and (not math.isfinite(mean) or not 0 <= mean <= 1):
            raise ValueError("invalid area fraction")
        selected = [r for r in record["threshold_sensitivity"] if r["threshold"] == threshold]
        if len(selected) != 1:
            raise ValueError("missing/duplicate threshold")
        suitable = selected[0]["suitable_hours"]
        segments = selected[0]["continuous_segments"][f"{duration_hours}_hours"]
        if not isinstance(suitable, int) or not 0 <= suitable <= valid:
            raise ValueError("suitable hours outside valid hours")
        if not isinstance(segments, int) or not 0 <= segments <= suitable // duration_hours:
            raise ValueError("impossible maximal-segment count")
        fraction = suitable / valid if valid else None
        declared = selected[0]["suitable_hour_fraction"]
        if (declared is None) != (fraction is None) or (
            fraction is not None and not math.isclose(fraction, declared, abs_tol=1e-12)
        ):
            raise ValueError("declared suitable-hour fraction inconsistent")
        limiting = record["limiting_factor"]
        row = {
            "burn_id": record["burn_id"], "year": record["year"],
            "metric_hours": total, "valid_hours": valid,
            "coverage_fraction": valid / total, "mean_area_fraction": mean,
            "threshold": threshold, "suitable_hours": suitable,
            "suitable_hour_fraction": fraction,
            "maximal_segments_at_least_duration": segments,
            "duration_hours": duration_hours,
            "annual_limiting_constraint": limiting["constraint"],
            "annual_limiting_failure_fraction": limiting.get("failure_fraction_of_valid_weighted_cell_hours"),
            "rule_reference": {"prescription_workbook_sha256": record["rule_sha256"],
                               "condition_key": limiting["constraint"],
                               "original_workbook_location": "not_in_compact; no fabricated cell reference"},
        }
        table.append(row)
        grouped[record["burn_id"]].append(row)
    periods = []
    for burn_id, rows in grouped.items():
        valid_sum = sum(row["valid_hours"] for row in rows)
        suitable_sum = sum(row["suitable_hours"] for row in rows)
        weighted = math.fsum((row["mean_area_fraction"] or 0) * row["valid_hours"] for row in rows)
        periods.append({
            "burn_id": burn_id, "years": [row["year"] for row in rows],
            "valid_hours": valid_sum, "metric_hours": sum(row["metric_hours"] for row in rows),
            "valid_hour_weighted_mean_area_fraction": weighted / valid_sum if valid_sum else None,
            "suitable_hours": suitable_sum,
            "suitable_hour_fraction": suitable_sum / valid_sum if valid_sum else None,
            "annual_segment_sum_no_cross_year_stitch": sum(row["maximal_segments_at_least_duration"] for row in rows),
            "annual_winner_year_counts_not_pooled_limiting_factor": dict(sorted(Counter(
                row["annual_limiting_constraint"] for row in rows).items())),
        })
    comparisons = []
    lookup = {(row["burn_id"], row["year"]): row for row in table}
    for row in table:
        key = (reference_burn_id or row["burn_id"], reference_year or row["year"])
        if key == (row["burn_id"], row["year"]):
            continue
        baseline = lookup.get(key)
        if baseline is None:
            raise ValueError("reference is not covered; no fallback")
        a, b = row["mean_area_fraction"], baseline["mean_area_fraction"]
        comparisons.append({
            "burn_id": row["burn_id"], "year": row["year"],
            "reference_burn_id": key[0], "reference_year": key[1],
            "mean_area_fraction_delta_percentage_points": 100 * (a - b) if a is not None and b is not None else None,
            "suitable_hours_delta": (row["suitable_hours"] - baseline["suitable_hours"]
                                     if row["valid_hours"] and baseline["valid_hours"] else None),
            "valid_hours": row["valid_hours"], "reference_valid_hours": baseline["valid_hours"],
            "equal_hour_denominator": row["valid_hours"] == baseline["valid_hours"],
        })
    explanations = []
    for row in table:
        mean_text = "unavailable" if row["mean_area_fraction"] is None else f"{row['mean_area_fraction']:.6f}"
        observation = (
            f"At descriptive area cutoff {threshold}, {row['suitable_hours']} hours qualify; "
            f"{row['maximal_segments_at_least_duration']} maximal annual segments last "
            f"at least {duration_hours} hours. "
            if row["valid_hours"] else
            "No valid hours were available; qualifying hours and segment comparisons are unavailable, "
            "not evidence of zero windows. "
        )
        explanations.append(
            f"{row['burn_id']} / {row['year']}: mean qualifying-area fraction {mean_text} "
            f"over {row['valid_hours']}/{row['metric_hours']} valid hours. {observation}"
            "Largest recorded annual weighted failure: "
            f"{row['annual_limiting_constraint']} (stored winner; uniqueness not known); prescription workbook "
            f"{row['rule_reference']['prescription_workbook_sha256']}. Not a pooled-period cause, "
            "field measurement, approval or safety recommendation."
        )
    result = {key: value for key, value in envelope.result.items() if key != "records"}
    result.update({"view": "compare", "annual_table": table, "period_summaries": periods,
                   "comparisons": comparisons, "explanations": explanations,
                   "provenance": {key: next(iter(values)) for key, values in provenance.items()},
                   "template_id": "climatology-comparison-v1",
                   "source_fields": ["weighted_suitable_area_fraction.mean", "valid_hours",
                                     "threshold_sensitivity", "limiting_factor.constraint", "rule_sha256"],
                   "method": "deterministic_compact_arithmetic_and_template_no_LLM"})
    return envelope.model_copy(update={"result": result, "constraints": [
        *envelope.constraints,
        "annual fractions are valid-hour weighted, never hectares or burn outcomes",
        "annual segment sums do not join December/January; annual medians are not pooled",
        "annual limiting winners do not reveal a pooled-period limiting factor",
    ]})
