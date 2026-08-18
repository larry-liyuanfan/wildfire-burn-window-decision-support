from __future__ import annotations

import json
from pathlib import Path

from burnwindows.tools import find_burn_windows


def test_golden_find_windows(core_prescription) -> None:
    fixture = json.loads(
        (Path(__file__).parent / "golden" / "tool_cases.json").read_text(encoding="utf-8")
    )
    case = fixture["find_burn_windows"]
    result = find_burn_windows(
        times=case["times"],
        data={
            "temperature_c": case["temperature_c"],
            "relative_humidity_pct": case["relative_humidity_pct"],
        },
        prescription=core_prescription,
        min_duration_hours=case["min_duration_hours"],
        data_version="golden-v1",
    )
    assert [item["duration_hours"] for item in result.result["windows"]] == case[
        "expected_durations"
    ]

