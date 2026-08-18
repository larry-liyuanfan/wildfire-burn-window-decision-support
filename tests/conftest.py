from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from burnwindows.models import Bound, Condition, Prescription, ScheduleCandidate


@pytest.fixture
def core_prescription() -> Prescription:
    return Prescription(
        burn_class="fixture",
        conditions=[
            Condition(
                field="Temperature",
                variable="temperature_c",
                unit="degC",
                lower=Bound(value=15),
                upper=Bound(value=25),
                source_text="15-25",
            ),
            Condition(
                field="RelativeHumidity",
                variable="relative_humidity_pct",
                unit="%",
                lower=Bound(value=35),
                upper=Bound(value=60),
                source_text="35-60",
            ),
        ],
        source="synthetic-test-fixture",
    )


@pytest.fixture
def schedule_candidates() -> list[ScheduleCandidate]:
    start = datetime(2026, 4, 1, 8, tzinfo=timezone.utc)
    return [
        ScheduleCandidate(
            id="a",
            region="east",
            start=start,
            end=start + timedelta(hours=4),
            area_hectares=10,
            robustness=1.0,
        ),
        ScheduleCandidate(
            id="b",
            region="east",
            start=start + timedelta(hours=1),
            end=start + timedelta(hours=5),
            area_hectares=20,
            robustness=1.0,
        ),
        ScheduleCandidate(
            id="c",
            region="west",
            start=start + timedelta(hours=6),
            end=start + timedelta(hours=9),
            area_hectares=8,
            robustness=1.0,
        ),
    ]
