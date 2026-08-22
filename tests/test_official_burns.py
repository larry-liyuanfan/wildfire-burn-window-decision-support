from urllib.parse import parse_qs, urlparse

import pytest

from burnwindows.official_burns import (
    PLANNED_BURNS_URL,
    build_delivery_summary,
    build_spatial_delivery_summary,
    fetch_arcgis_rows,
    fetch_district_delivery,
)

PLAN_ROWS = [
    {
        "OBJECTID": 1,
        "TREAT_NO": "LM-MGF-001",
        "TREAT_NAME": "Fixture burn",
        "JFMPYEAR": "2025",
        "TREAT_TYPE": "FUEL REDUCTION",
        "DISTRICT": "Murray Goldfields",
        "REGION": "Loddon Mallee",
        "LAND_OBJECTIVE": "Fuel reduction",
        "HECTARES": 100.0,
        "EVENTID": 10,
    },
    {
        "OBJECTID": 2,
        "TREAT_NO": "LM-MGF-002",
        "TREAT_NAME": "Unmatched burn",
        "JFMPYEAR": "2026",
        "TREAT_TYPE": "ECOLOGICAL",
        "DISTRICT": "Murray Goldfields",
        "REGION": "Loddon Mallee",
        "LAND_OBJECTIVE": "Ecology",
        "HECTARES": 50.0,
        "EVENTID": 11,
    },
]

OUTCOME_ROWS = [
    {
        "OBJECTID": 9,
        "FIRETYPE": "Burn",
        "SEASON": 2025,
        "FIRE_NO": "LM-MGF-001",
        "NAME": "Fixture burn",
        "START_DATE": 1_746_835_200_000,
        "TREATMENT_TYPE": "FUEL REDUCTION",
        "AREA_HA": 80.0,
        "DISTRICT_ID": "Loddon Mallee - Murray Goldfields",
        "REGION": "Loddon Mallee",
        "LEAD_AGENCY": "FFMVic",
    }
]


def _transport(url: str) -> dict:
    parsed = urlparse(url)
    offset = int(parse_qs(parsed.query).get("resultOffset", [0])[0])
    rows = PLAN_ROWS if url.startswith(PLANNED_BURNS_URL) else OUTCOME_ROWS
    page = rows[offset : offset + 1]
    return {
        "features": [{"attributes": row} for row in page],
        "exceededTransferLimit": offset + len(page) < len(rows),
    }


def test_arcgis_adapter_paginates_and_hashes_attributes() -> None:
    rows, provenance = fetch_arcgis_rows(
        PLANNED_BURNS_URL,
        where="DISTRICT='Murray Goldfields'",
        out_fields=list(PLAN_ROWS[0]),
        page_size=1,
        transport=_transport,
    )
    assert rows == PLAN_ROWS
    assert provenance["record_count"] == 2
    assert len(provenance["attributes_sha256"]) == 64


def test_delivery_summary_uses_real_area_but_labels_cost_and_crew_as_proxies() -> None:
    plans, outcomes, provenance = fetch_district_delivery(transport=_transport)
    result = build_delivery_summary(
        plans,
        outcomes,
        direct_cost_aud=1_000.0,
        statewide_treated_hectares=100.0,
    )
    assert provenance["plans"]["record_count"] == 2
    assert result["plan_feature_count"] == 2
    assert result["plan_unit_count"] == 2
    assert result["matched_burn_unit_count"] == 1
    assert result["matched_planned_hectares"] == 100.0
    assert result["matched_treated_hectares"] == 80.0
    assert result["aggregate_treated_to_planned_ratio"] == pytest.approx(0.8)
    assert result["economic_proxy"]["matched_area_direct_cost_proxy_aud"] == 800.0
    assert "not an observed burn-unit cost" in result["economic_proxy"]["interpretation"]
    assert "not actual crew rosters" in result["crew_scenarios"]["interpretation"]


def test_adapter_rejects_non_official_host() -> None:
    with pytest.raises(ValueError, match="official FFMVic"):
        fetch_arcgis_rows(
            "https://example.com/layer",
            where="1=1",
            out_fields=["OBJECTID"],
            transport=_transport,
        )


def test_spatial_delivery_uses_polygon_intersection_not_attribute_ratio() -> None:
    planned = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"TREAT_NO": "burn-1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [144.0, -37.0],
                            [144.02, -37.0],
                            [144.02, -36.98],
                            [144.0, -36.98],
                            [144.0, -37.0],
                        ]
                    ],
                },
            }
        ],
    }
    outcome = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"FIRE_NO": "burn-1"},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [144.01, -36.99],
                            [144.03, -36.99],
                            [144.03, -36.97],
                            [144.01, -36.97],
                            [144.01, -36.99],
                        ]
                    ],
                },
            }
        ],
    }
    result = build_spatial_delivery_summary(planned, outcome)
    assert result["matched_burn_unit_count"] == 1
    assert result["aggregate_plan_area_covered"] == pytest.approx(0.25, rel=0.02)
    assert result["aggregate_treated_area_inside_plan"] == pytest.approx(0.25, rel=0.02)
