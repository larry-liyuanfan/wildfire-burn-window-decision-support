from copy import deepcopy

import pytest

from scripts.build_public_proxy_aggregate_record import build_public_record


def _summary() -> dict:
    return {
        "evidence_status": "verified-real-proxy-complete-prescription-by-this-run",
        "git_sha": "annual",
        "year_count": 51,
        "prescription_scope": {
            "complete": True,
            "evaluated_condition_count": 8,
            "excluded_unmapped_condition_count": 0,
        },
        "derived_fuel_inputs": {"observed_on_site": False},
        "region_scope": {"source_path": "/private/boundary.geojson"},
        "quality_gate": {
            "complete_expected_year_set": True,
            "single_exact_git_sha": True,
            "single_derived_fuel_input_contract": True,
        },
    }


def _build(summary: dict) -> dict:
    return build_public_record(
        summary,
        summary_sha256="summary",
        aggregation_git_sha="aggregate",
        array_job_id="array",
        aggregate_job_id="aggregate-job",
        array_elapsed_total_seconds=100,
        array_max_rss_kib=200,
        aggregate_elapsed_seconds=3,
        aggregate_max_rss_kib=50,
    )


def test_public_proxy_aggregate_redacts_paths_and_keeps_lineage() -> None:
    record = _build(_summary())
    assert record["summary"]["region_scope"]["source_path"] == (
        "official-district-boundary.geojson"
    )
    assert "/private/" not in str(record)
    assert record["evidence_identity"]["annual_run_git_sha"] == "annual"


def test_public_proxy_aggregate_fails_closed_on_incomplete_scope() -> None:
    summary = deepcopy(_summary())
    summary["prescription_scope"]["complete"] = False
    with pytest.raises(ValueError, match="every compiled"):
        _build(summary)
