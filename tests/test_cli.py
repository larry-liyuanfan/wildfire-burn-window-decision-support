from __future__ import annotations

import json

import pytest

from burnwindows.cli import _load_threshold_scenarios


def test_threshold_scenario_file_is_sorted_and_validated(tmp_path, core_prescription) -> None:
    path = tmp_path / "scenarios.json"
    path.write_text(
        json.dumps(
            {
                "humidity_wider": {"RelativeHumidity": 5},
                "temperature_narrower": {"Temperature": -2},
            }
        ),
        encoding="utf-8",
    )

    scenarios = _load_threshold_scenarios(path, core_prescription)

    assert list(scenarios) == ["humidity_wider", "temperature_narrower"]
    assert scenarios["humidity_wider"] == {"RelativeHumidity": 5.0}


def test_threshold_scenario_file_rejects_unmapped_fields(tmp_path, core_prescription) -> None:
    path = tmp_path / "scenarios.json"
    path.write_text(
        json.dumps({"invented_input": {"FMCSurfaceInside": 1}}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="not mapped"):
        _load_threshold_scenarios(path, core_prescription)
