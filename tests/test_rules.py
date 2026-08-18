from __future__ import annotations

import openpyxl

from burnwindows.rules import (
    compile_record,
    compile_records,
    load_prescriptions,
    parse_kbdi,
    parse_threshold,
)


def test_range_is_inclusive() -> None:
    condition = parse_threshold("8-20", field="x", variable="x", unit=None, status="mapped")
    assert condition.lower.value == 8
    assert condition.lower.inclusive
    assert condition.upper.value == 20
    assert condition.upper.inclusive


def test_strict_upper_bound_is_preserved() -> None:
    condition = parse_threshold("<30", field="x", variable="x", unit=None, status="mapped")
    assert condition.upper.value == 30
    assert not condition.upper.inclusive


def test_lower_bound_is_parsed() -> None:
    condition = parse_threshold(">=25", field="x", variable="x", unit=None, status="mapped")
    assert condition.lower.value == 25
    assert condition.lower.inclusive
    assert condition.upper is None


def test_seasonal_kbdi_keeps_unclear_semantics_unresolved() -> None:
    conditions, unresolved = parse_kbdi("Spring: <=20, Autumn: <=40, Fallen: <=100")
    assert [condition.season for condition in conditions] == ["spring", "autumn"]
    assert unresolved == {"KBDI:Fallen": "<=100"}


def test_compile_record_never_silently_drops_unknown_fields() -> None:
    prescription = compile_record(
        {
            "BurnClass": "test",
            "Temperature": "12-28",
            "FDIIgnitionDay2": "<=12",
            "FMCElevated": "2016-12-01",
        }
    )
    assert len(prescription.conditions) == 1
    assert prescription.unresolved == {
        "FDIIgnitionDay2": "<=12",
        "FMCElevated": "2016-12-01",
    }


def test_duplicate_burn_classes_are_rejected() -> None:
    records = [{"BurnClass": "same", "Temperature": "<=20"}] * 2
    try:
        compile_records(records)
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_loader_compiles_all_43_fixture_rows(tmp_path) -> None:
    path = tmp_path / "fixture.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["BurnClass", "Temperature", "RelativeHumidity"])
    for index in range(43):
        sheet.append([f"class-{index}", "15-25", ">=35"])
    workbook.save(path)
    prescriptions = load_prescriptions(path)
    assert len(prescriptions) == 43
    assert sum(len(item.conditions) for item in prescriptions) == 86
