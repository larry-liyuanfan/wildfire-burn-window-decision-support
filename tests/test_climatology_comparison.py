import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_burn_unit_climatology import _full_compact_artifact

from burnwindows.burn_unit_climatology import publish_compact_artifact
from burnwindows.climatology_comparison import comparison_view
from burnwindows.mcp_server import MCPClimatologyRequest
from burnwindows.models import ToolEnvelope


def annual(year=2020, valid=100, mean=0.2, burn_id="unit-a"):
    return {"burn_id": burn_id, "year": year, "metric_hours": 200, "valid_hours": valid,
            "weighted_suitable_area_fraction": {"mean": mean},
            "threshold_sensitivity": [{"threshold": 0.8, "suitable_hours": valid // 2,
                "suitable_hour_fraction": (valid // 2) / valid if valid else None,
                "continuous_segments": {"4_hours": valid // 10}}],
            "limiting_factor": {"constraint": "Temperature:0"},
            "data_sha256": "a" * 64, "rule_sha256": "b" * 64,
            "spatial_sha256": "c" * 64, "git_sha": "d" * 40}


def envelope(records):
    return ToolEnvelope(status="ok", data_version="fixture", source="fixture",
                        warnings=["precipitation field absent; FMC rain guard was not applied"],
                        constraints=["original constraints"], result={"records": records,
                        "record_count": len(records), "publication_boundary": ["no safety claim"]})


def test_weighted_period_not_mean_of_means_and_pp_not_percent():
    value = envelope([annual(), annual(2021, 50, 0.8)])
    before = copy.deepcopy(value.model_dump())
    result = comparison_view(value, reference_year=2020)
    assert result.result["period_summaries"][0]["valid_hour_weighted_mean_area_fraction"] == pytest.approx(0.4)
    assert result.result["comparisons"][0]["mean_area_fraction_delta_percentage_points"] == pytest.approx(60)
    assert not result.result["comparisons"][0]["equal_hour_denominator"]
    assert value.model_dump() == before
    assert result.warnings == value.warnings
    assert result.result["annual_table"][0]["rule_reference"]["prescription_workbook_sha256"] == "b" * 64
    assert result.result["publication_boundary"] == ["no safety claim"]


def test_zero_valid_is_unknown_not_zero():
    result = comparison_view(envelope([annual(valid=0, mean=None)]))
    assert result.result["period_summaries"][0]["valid_hour_weighted_mean_area_fraction"] is None
    assert "unavailable" in result.result["explanations"][0]


@pytest.mark.parametrize("bad", ["mixed_rule", "duplicate", "fraction", "segments", "missing_mean", "nan"])
def test_inconsistent_source_fails_closed(bad):
    first, second = annual(), annual(2021)
    if bad == "mixed_rule":
        second["rule_sha256"] = "e" * 64
    elif bad == "duplicate":
        second["year"] = 2020
    elif bad == "fraction":
        second["threshold_sensitivity"][0]["suitable_hour_fraction"] = 0.9
    elif bad == "segments":
        second["threshold_sensitivity"][0]["continuous_segments"]["4_hours"] = 500
    elif bad == "missing_mean":
        second["weighted_suitable_area_fraction"]["mean"] = None
    else:
        second["weighted_suitable_area_fraction"]["mean"] = float("nan")
    with pytest.raises(ValueError):
        comparison_view(envelope([first, second]))


def test_missing_reference_and_partial_never_fallback():
    value = envelope([annual()])
    with pytest.raises(ValueError, match="reference"):
        comparison_view(value, reference_burn_id="missing")
    value.status = "partial"
    with pytest.raises(ValueError):
        comparison_view(value)


def test_comparison_schema_rejects_override_and_out_of_range_reference():
    request = {"artifact_id": "fixture", "burn_ids": ["unit-a"], "view": "compare",
               "year_start": 2020, "year_end": 2021}
    for change in ({"threshold": 0.7}, {"reference_year": 2019},
                   {"reference_burn_id": "unknown"}, {"rule_override": "permit"}):
        with pytest.raises(ValidationError):
            MCPClimatologyRequest.model_validate({**request, **change})


def test_three_real_mcp_roundtrips_on_synthetic_contract_fixture(tmp_path):
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / "fixture.json"
    source.write_text(json.dumps(_full_compact_artifact()), encoding="utf-8")
    publication = publish_compact_artifact(source, output_dir=tmp_path / "published",
                                           artifact_id="fixture")
    subprocess.run([
        sys.executable, str(root / "scripts/demo_mcp_comparison.py"),
        "--artifact-catalog", publication["catalog_path"], "--artifact-id", "fixture",
        "--burn-id", "burn-000", "--expected-catalog-sha256", publication["catalog_sha256"],
        "--expected-artifact-sha256", publication["artifact_sha256"],
        "--output", str(tmp_path / "redacted.json"),
        "--restricted-detail-output", str(tmp_path / "fixture-detail.json"),
        "--evidence-kind", "synthetic-contract-fixture",
    ], check=True, timeout=60, cwd=root, env={**os.environ, "PYTHONPATH": str(root / "src")})
    report = json.loads((tmp_path / "redacted.json").read_text())
    assert report["tools_call_roundtrips"] == 6
    assert [case["row_count"] for case in report["cases"]] == [2, 2, 5]
    assert report["records_exported"] is False
    assert all(case["status"] == "passed" for case in report["cases"])
