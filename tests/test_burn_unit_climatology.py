from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from burnwindows.burn_unit_climatology import (
    RAIN_GUARD_WARNING,
    SparseBurnOverlay,
    aggregate_annual_artifacts,
    aggregate_grid_year,
    compare_annual_recomputation,
    count_continuous_segments,
    publish_compact_artifact,
    require_sha256,
    validate_compact_artifact,
)
from burnwindows.service import create_app

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _overlay() -> dict:
    return {
        "grid_shape": [1, 3],
        "zero_coverage_burn_unit_count": 0,
        "burn_units": [
            {"burn_id": "burn-a", "status": "ok"},
            {"burn_id": "burn-b", "status": "ok"},
        ],
        "weights": [
            {
                "burn_id": "burn-a",
                "latitude_index": 0,
                "longitude_index": 0,
                "overlap_hectares": 1.0,
            },
            {
                "burn_id": "burn-a",
                "latitude_index": 0,
                "longitude_index": 1,
                "overlap_hectares": 3.0,
            },
            {
                "burn_id": "burn-b",
                "latitude_index": 0,
                "longitude_index": 2,
                "overlap_hectares": 2.0,
            },
        ],
    }


def test_sparse_weights_are_normalised_and_match_direct_reference() -> None:
    overlay = SparseBurnOverlay.from_mapping(
        _overlay(), expected_burn_unit_count=2, expected_weight_row_count=3
    )
    values = np.asarray([[1.0, 0.0, 1.0], [0.0, 1.0, 0.0]])
    assert overlay.weight_sums().tolist() == pytest.approx([1.0, 1.0])
    assert np.allclose(overlay.aggregate(values), [[0.25, 1.0], [0.75, 0.0]])
    assert np.array_equal(overlay.aggregate(values), overlay.aggregate_direct(values))


def test_continuous_segments_count_maximal_runs() -> None:
    mask = [True, True, True, False, True, True, False]
    assert count_continuous_segments(mask, 2) == 2
    assert count_continuous_segments(mask, 3) == 1
    assert count_continuous_segments(mask, 4) == 0


def test_sha_contract_rejects_a_plausible_but_65_character_value() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        require_sha256("a" * 65, field="data_sha256")


def test_annual_records_keep_continuous_fraction_provenance_and_warning() -> None:
    overlay = SparseBurnOverlay.from_mapping(_overlay())
    suitable = np.asarray(
        [
            [True, False, True],
            [True, True, False],
            [False, False, True],
            [True, True, True],
        ]
    )
    valid = np.ones_like(suitable)
    masks = {
        "Temperature:0": np.asarray(
            [
                [True, False, True],
                [True, True, True],
                [False, False, True],
                [True, True, True],
            ]
        ),
        "RelativeHumidity:1": np.ones_like(suitable),
    }
    sparse_records, sparse_fraction, sparse_valid = aggregate_grid_year(
        year=2020,
        overlay=overlay,
        suitable=suitable,
        all_conditions_valid=valid,
        condition_masks=masks,
        data_sha256=SHA_A,
        rule_sha256=SHA_B,
        spatial_sha256=SHA_C,
        code_sha="commit-1",
        warnings=[RAIN_GUARD_WARNING],
    )
    direct_records, direct_fraction, direct_valid = aggregate_grid_year(
        year=2020,
        overlay=overlay,
        suitable=suitable,
        all_conditions_valid=valid,
        condition_masks=masks,
        data_sha256=SHA_A,
        rule_sha256=SHA_B,
        spatial_sha256=SHA_C,
        code_sha="commit-1",
        warnings=[RAIN_GUARD_WARNING],
        method="direct",
    )
    assert sparse_records[0]["weighted_suitable_area_fraction"]["mean"] == pytest.approx(
        0.5625
    )
    assert sparse_records[0]["valid_hours"] == 4
    assert sparse_records[0]["limiting_factor"]["constraint"] == "Temperature:0"
    assert sparse_records[0]["data_sha256"] == SHA_A
    assert RAIN_GUARD_WARNING in sparse_records[0]["warnings"]
    comparison = compare_annual_recomputation(
        expected_records=sparse_records,
        expected_hourly_fraction=sparse_fraction,
        expected_valid_hours=sparse_valid,
        actual_records=direct_records,
        actual_hourly_fraction=direct_fraction,
        actual_valid_hours=direct_valid,
    )
    assert comparison["status"] == "passed"


def _full_compact_artifact() -> dict:
    records = []
    warnings = [RAIN_GUARD_WARNING]
    for burn_index in range(176):
        for year in range(1973, 2024):
            records.append(
                {
                    "burn_id": f"burn-{burn_index:03d}",
                    "year": year,
                    "metric_hours": 8760,
                    "valid_hours": 8760,
                    "weighted_suitable_area_fraction": {"mean": 0.25},
                    "threshold_sensitivity": [
                        {
                            "threshold": threshold,
                            "suitable_hours": 1,
                            "suitable_hour_fraction": 1 / 8760,
                            "continuous_segments": {
                                "2_hours": 0,
                                "4_hours": 0,
                                "6_hours": 0,
                            },
                        }
                        for threshold in (0.5, 0.8, 1.0)
                    ],
                    "limiting_factor": {"constraint": "Temperature:0"},
                    "data_sha256": SHA_A,
                    "rule_sha256": SHA_B,
                    "spatial_sha256": SHA_C,
                    "git_sha": "commit-1",
                    "warnings": warnings,
                }
            )
    return {
        "schema_version": "1.0",
        "artifact_kind": "burn-unit-climatology-compact",
        "year_start": 1973,
        "year_end": 2023,
        "year_count": 51,
        "burn_unit_count": 176,
        "annual_record_count": len(records),
        "provenance": {
            "data_sha256": SHA_A,
            "rule_sha256": SHA_B,
            "spatial_sha256": SHA_C,
            "git_sha": "commit-1",
        },
        "records": records,
        "quality_gate": {
            "complete_176_burn_ids": True,
            "complete_51_years": True,
            "single_sha": True,
        },
        "publication_boundary": ["descriptive only"],
    }


def test_compact_artifact_service_is_allowlisted_and_read_only(tmp_path: Path) -> None:
    source = tmp_path / "aggregate.json"
    source.write_text(json.dumps(_full_compact_artifact()), encoding="utf-8")
    publication = publish_compact_artifact(
        source, output_dir=tmp_path / "published", artifact_id="compact-v1"
    )
    artifact = json.loads(Path(publication["artifact_path"]).read_text(encoding="utf-8"))
    assert validate_compact_artifact(artifact)["annual_record_count"] == 176 * 51

    client = TestClient(create_app(artifact_catalog=publication["catalog_path"]))
    response = client.post(
        "/api/tools/get_burn_unit_climatology:invoke",
        json={
            "arguments": {
                "artifact_id": "compact-v1",
                "burn_ids": ["burn-000"],
                "year_start": 2020,
                "year_end": 2021,
            }
        },
    )
    arbitrary_path = client.post(
        "/api/tools/get_burn_unit_climatology:invoke",
        json={
            "arguments": {
                "artifact_id": "compact-v1",
                "artifact_path": str(source),
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["provenance"]["status"] == "artifact_verified"
    assert response.json()["result"]["record_count"] == 2
    assert arbitrary_path.status_code == 422


def test_annual_aggregate_requires_complete_cartesian_product_and_one_sha(
    tmp_path: Path,
) -> None:
    full = _full_compact_artifact()
    for year in range(1973, 2024):
        year_dir = tmp_path / f"year-{year}"
        year_dir.mkdir()
        annual = {
            "artifact_kind": "burn-unit-climatology-annual",
            "year": year,
            "annual_records": [row for row in full["records"] if row["year"] == year],
            "quality_gate": {"complete": True},
        }
        (year_dir / "metrics.json").write_text(json.dumps(annual), encoding="utf-8")
        (year_dir / "run_manifest.json").write_text("{}", encoding="utf-8")
        (year_dir / "error_cases.json").write_text("[]", encoding="utf-8")
    compact = aggregate_annual_artifacts(
        tmp_path, expected_years=range(1973, 2024), expected_burn_unit_count=176
    )
    assert compact["annual_record_count"] == 176 * 51
    assert validate_compact_artifact(compact)["status"] == "passed"

    changed_path = tmp_path / "year-2020" / "metrics.json"
    changed = json.loads(changed_path.read_text(encoding="utf-8"))
    changed["annual_records"][0]["data_sha256"] = "d" * 64
    changed_path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="mixed SHA"):
        aggregate_annual_artifacts(
            tmp_path, expected_years=range(1973, 2024), expected_burn_unit_count=176
        )


def test_overlay_rejects_zero_coverage_without_nearest_fallback() -> None:
    overlay = _overlay()
    overlay["burn_units"][0]["status"] = "zero_coverage"
    with pytest.raises(ValueError, match="forbids zero coverage"):
        SparseBurnOverlay.from_mapping(overlay)


def test_spartan_chain_is_pinned_to_authorised_account_and_output_root() -> None:
    repository = Path(__file__).parents[1]
    scripts = [
        repository / "spartan" / name
        for name in (
            "run_burn_unit_climatology_preflight.sbatch",
            "run_burn_unit_climatology_pilot.sbatch",
            "compare_burn_unit_climatology_2020.sbatch",
            "run_burn_unit_climatology_year_array.sbatch",
            "aggregate_burn_unit_climatology.sbatch",
            "publish_burn_unit_climatology.sbatch",
        )
    ]
    expected_root = (
        "/data/gpfs/projects/punim1257/Group44/outputs/"
        "flare-burn-id-climatology-20260903"
    )
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert "#SBATCH --account=punim1257" in text
        assert expected_root in text
        assert "FLARE_GIT_SHA" in text
        assert "spartan-trip" not in text
        assert "yzhang3504" not in text
    assert "#SBATCH --array=1973-2023%4" in scripts[3].read_text(encoding="utf-8")


def test_public_execution_record_is_redacted_complete_and_truth_bounded() -> None:
    repository = Path(__file__).parents[1]
    record_path = (
        repository
        / "artifacts"
        / "public"
        / "vicclim6_murray_goldfields_burn_id_climatology_20260903.json"
    )
    record_text = record_path.read_text(encoding="utf-8")
    record = json.loads(record_text)

    assert record["implementation"]["git_sha"] == (
        "bf90d0afd1012f893369a2ef87f72133892d6bd9"
    )
    assert record["spartan"]["annual_array"]["completed_tasks"] == 51
    assert record["spartan"]["annual_array"]["failed_tasks"] == 0
    assert record["results"]["annual_record_count"] == 176 * 51
    assert record["results"]["direct_comparison"]["maximum_absolute_difference"] == 0
    assert all(record["quality_gate"].values())
    assert record["compact_artifact"]["bytes_published_to_git"] is False
    assert record["recorded_quality_failure"]["hidden"] is False
    assert "/data/gpfs/" not in record_text
    assert "FMS-Prescriptions_2.xlsx" not in record_text
