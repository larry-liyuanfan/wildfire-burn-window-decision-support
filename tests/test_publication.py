from scripts.build_public_sensitivity_record import build_public_record


def test_public_sensitivity_record_drops_paths_and_annual_rows() -> None:
    summary = {
        "evidence_status": "verified-real-partial-prescription-by-this-run",
        "git_sha": "a" * 40,
        "aggregation_git_sha": "b" * 40,
        "burn_class": "fixture",
        "region_scope": {
            "label": "district",
            "selected_grid_cells": 5,
            "source_path": "/restricted/boundary.geojson",
        },
        "year_start": 1973,
        "year_end": 2023,
        "year_count": 51,
        "evaluated_space_time_cells": 100,
        "provisional_pass_cells": 10,
        "provisional_pass_rate": 0.1,
        "minimum_duration_endpoints": {"2": 3},
        "threshold_sensitivity": {
            "semantics": "absolute deltas",
            "constraints": ["partial"],
            "annual_effect_interpretation": "descriptive",
            "scenarios": [
                {
                    "scenario": "wider",
                    "overrides": {"Temperature": 2.0},
                    "provisional_pass_cells": 12,
                    "provisional_pass_rate": 0.12,
                    "absolute_rate_change": 0.02,
                    "relative_rate_change": 0.2,
                    "minimum_duration_endpoints": {"2": 4},
                    "annual_effects": [{"year": 1973, "absolute_rate_change": 0.01}],
                    "annual_effect_summary": {"positive_year_count": 51},
                }
            ],
        },
        "quality_gate": {"complete_expected_year_set": True},
    }

    result = build_public_record(summary, summary_file="summary.json", summary_sha256="c" * 64)

    encoded = str(result)
    assert "/restricted/" not in encoded
    assert "annual_effects" not in encoded
    assert result["scope"]["region"] == {"label": "district", "selected_grid_cells": 5}
