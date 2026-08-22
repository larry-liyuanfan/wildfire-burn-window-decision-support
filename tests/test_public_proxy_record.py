from copy import deepcopy

import pytest

from scripts.build_public_proxy_record import build_public_record


def _fixture() -> tuple[dict, dict]:
    metrics = {
        "evidence_status": "verified-real-proxy-complete-prescription-by-this-run",
        "prescription_scope": {
            "complete": True,
            "compiled_condition_count": 8,
            "evaluated_condition_count": 8,
            "excluded_unmapped_condition_count": 0,
        },
        "derived_fuel_inputs": {"observed_on_site": False},
        "region_scope": {"source_path": "/private/boundary.geojson"},
    }
    manifest = {
        "created_at_utc": "2026-08-22T00:00:00+00:00",
        "git_sha": "abc123",
        "runtime": {"slurm_job_id": "1", "python": "3.11"},
        "inputs": [
            {"path": "/private/rules.xlsx", "sha256": "rules"},
            {"path": "/private/boundary.geojson", "sha256": "boundary"},
        ],
    }
    return metrics, manifest


def test_public_proxy_record_keeps_identity_but_redacts_paths() -> None:
    metrics, manifest = _fixture()
    record = build_public_record(
        metrics,
        manifest,
        metrics_sha256="metrics",
        manifest_sha256="manifest",
        elapsed="00:01:16",
        compute_max_rss_kib=792724,
    )
    assert record["run"]["input_identity"]["prescription_workbook_sha256"] == "rules"
    assert record["run"]["compute_max_rss_kib"] == 792724
    assert "/private/" not in str(record)
    assert record["metrics"]["region_scope"]["source_path"] == (
        "official-district-boundary.geojson"
    )


def test_public_proxy_record_rejects_partial_run() -> None:
    metrics, manifest = _fixture()
    metrics = deepcopy(metrics)
    metrics["prescription_scope"]["excluded_unmapped_condition_count"] = 1
    with pytest.raises(ValueError, match="every compiled"):
        build_public_record(
            metrics,
            manifest,
            metrics_sha256="metrics",
            manifest_sha256="manifest",
            elapsed="00:01:16",
            compute_max_rss_kib=792724,
        )
