"""Official FFMVic planned-burn and Fire History adapters."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import BurnOutcome, BurnUnit

PLANNED_BURNS_URL = "https://maps.ffm.vic.gov.au/arcgis/rest/services/pbns/MapServer/8"
FIRE_HISTORY_URL = "https://maps.ffm.vic.gov.au/arcgis/rest/services/pbns/MapServer/10"
RISK_MITIGATION_REPORT_URL = (
    "https://www.ffm.vic.gov.au/monitoring-evaluation-and-reporting/"
    "ffmvic-bushfire-risk-mitigation-update-2024-25"
)
CREW_GUIDANCE_URL = "https://www.ffm.vic.gov.au/media-releases/how-we-do-planned-burning"


def _default_transport(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "burn-window-evidence/0.1"})
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _canonical_hash(rows: Iterable[dict[str, Any]]) -> str:
    payload = json.dumps(list(rows), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fetch_arcgis_rows(
    layer_url: str,
    *,
    where: str,
    out_fields: list[str],
    page_size: int = 1000,
    transport: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch all attribute rows with explicit ArcGIS result-offset pagination."""

    if not layer_url.startswith("https://maps.ffm.vic.gov.au/"):
        raise ValueError("only the pinned official FFMVic host is accepted")
    if page_size < 1 or page_size > 1000:
        raise ValueError("page_size must be in [1, 1000]")
    load = transport or _default_transport
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        query = urlencode(
            {
                "where": where,
                "outFields": ",".join(out_fields),
                "returnGeometry": "false",
                "resultOffset": offset,
                "resultRecordCount": page_size,
                "orderByFields": "OBJECTID",
                "f": "json",
            }
        )
        payload = load(f"{layer_url}/query?{query}")
        if payload.get("error"):
            raise RuntimeError(f"ArcGIS query failed: {payload['error']}")
        page = [feature["attributes"] for feature in payload.get("features", [])]
        rows.extend(page)
        if not payload.get("exceededTransferLimit") and len(page) < page_size:
            break
        if not page:
            raise RuntimeError("ArcGIS pagination made no progress")
        offset += len(page)
    provenance = {
        "layer_url": layer_url,
        "where": where,
        "out_fields": out_fields,
        "record_count": len(rows),
        "attributes_sha256": _canonical_hash(rows),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    return rows, provenance


def fetch_arcgis_geojson(
    layer_url: str,
    *,
    where: str,
    out_fields: list[str],
    transport: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch a compact EPSG:4326 GeoJSON feature collection."""

    if not layer_url.startswith("https://maps.ffm.vic.gov.au/"):
        raise ValueError("only the pinned official FFMVic host is accepted")
    load = transport or _default_transport
    query = urlencode(
        {
            "where": where,
            "outFields": ",".join(out_fields),
            "returnGeometry": "true",
            "outSR": 4326,
            "resultRecordCount": 1000,
            "f": "geojson",
        }
    )
    payload = load(f"{layer_url}/query?{query}")
    if payload.get("error"):
        raise RuntimeError(f"ArcGIS GeoJSON query failed: {payload['error']}")
    features = payload.get("features", [])
    if not isinstance(features, list):
        raise TypeError("ArcGIS GeoJSON response has invalid features")
    canonical = json.dumps(features, sort_keys=True, separators=(",", ":"), default=str)
    provenance = {
        "layer_url": layer_url,
        "where": where,
        "out_fields": out_fields,
        "record_count": len(features),
        "geojson_features_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "crs": "EPSG:4326",
    }
    return {"type": "FeatureCollection", "features": features}, provenance


def _required(row: dict[str, Any], key: str) -> Any:
    value = row.get(key)
    if value is None or value == "":
        raise ValueError(f"official row lacks required field {key}")
    return value


def parse_burn_unit(row: dict[str, Any]) -> BurnUnit:
    return BurnUnit(
        burn_id=str(_required(row, "TREAT_NO")).strip(),
        name=str(_required(row, "TREAT_NAME")).strip(),
        jfmp_year=str(row["JFMPYEAR"]).strip() if row.get("JFMPYEAR") is not None else None,
        treatment_type=(
            str(row["TREAT_TYPE"]).strip() if row.get("TREAT_TYPE") is not None else None
        ),
        district=str(_required(row, "DISTRICT")).strip(),
        region=str(row["REGION"]).strip() if row.get("REGION") is not None else None,
        objective=(
            str(row["LAND_OBJECTIVE"]).strip() if row.get("LAND_OBJECTIVE") is not None else None
        ),
        planned_hectares=float(_required(row, "HECTARES")),
        event_id=int(row["EVENTID"]) if row.get("EVENTID") is not None else None,
    )


def parse_burn_outcome(row: dict[str, Any]) -> BurnOutcome:
    raw_start = row.get("START_DATE")
    start = (
        datetime.fromtimestamp(float(raw_start) / 1000.0, tz=timezone.utc)
        if raw_start is not None
        else None
    )
    return BurnOutcome(
        burn_id=str(_required(row, "FIRE_NO")).strip(),
        name=str(_required(row, "NAME")).strip(),
        season=int(row["SEASON"]) if row.get("SEASON") is not None else None,
        start=start,
        treatment_type=(
            str(row["TREATMENT_TYPE"]).strip() if row.get("TREATMENT_TYPE") is not None else None
        ),
        treated_hectares=float(_required(row, "AREA_HA")),
        district=str(_required(row, "DISTRICT_ID")).strip(),
        region=str(row["REGION"]).strip() if row.get("REGION") is not None else None,
        lead_agency=(
            str(row["LEAD_AGENCY"]).strip() if row.get("LEAD_AGENCY") is not None else None
        ),
    )


def fetch_district_delivery(
    *,
    planned_district: str = "Murray Goldfields",
    history_district: str = "Loddon Mallee - Murray Goldfields",
    transport: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[list[BurnUnit], list[BurnOutcome], dict[str, Any]]:
    plan_fields = [
        "OBJECTID",
        "TREAT_NO",
        "TREAT_NAME",
        "JFMPYEAR",
        "TREAT_TYPE",
        "DISTRICT",
        "REGION",
        "LAND_OBJECTIVE",
        "HECTARES",
        "EVENTID",
    ]
    outcome_fields = [
        "OBJECTID",
        "FIRETYPE",
        "SEASON",
        "FIRE_NO",
        "NAME",
        "START_DATE",
        "TREATMENT_TYPE",
        "AREA_HA",
        "DISTRICT_ID",
        "REGION",
        "LEAD_AGENCY",
    ]
    escaped_plan = planned_district.replace("'", "''")
    escaped_history = history_district.replace("'", "''")
    plan_rows, plan_provenance = fetch_arcgis_rows(
        PLANNED_BURNS_URL,
        where=f"DISTRICT='{escaped_plan}'",
        out_fields=plan_fields,
        transport=transport,
    )
    outcome_rows, outcome_provenance = fetch_arcgis_rows(
        FIRE_HISTORY_URL,
        where=f"FIRETYPE='Burn' AND DISTRICT_ID='{escaped_history}'",
        out_fields=outcome_fields,
        transport=transport,
    )
    plans = [parse_burn_unit(row) for row in plan_rows]
    outcomes = [parse_burn_outcome(row) for row in outcome_rows]
    return plans, outcomes, {"plans": plan_provenance, "outcomes": outcome_provenance}


def build_delivery_summary(
    plans: Iterable[BurnUnit],
    outcomes: Iterable[BurnOutcome],
    *,
    direct_cost_aud: float = 26_700_000.0,
    statewide_treated_hectares: float = 92_473.0,
) -> dict[str, Any]:
    """Align plan and outcome records by official burn identifier."""

    plan_rows = list(plans)
    outcome_rows = list(outcomes)
    unique_plans = list(
        {
            json.dumps(item.model_dump(mode="json"), sort_keys=True): item for item in plan_rows
        }.values()
    )
    unique_outcomes = list(
        {
            json.dumps(item.model_dump(mode="json"), sort_keys=True): item for item in outcome_rows
        }.values()
    )
    plans_by_id: dict[str, list[BurnUnit]] = defaultdict(list)
    for plan in unique_plans:
        plans_by_id[plan.burn_id].append(plan)
    outcomes_by_id: dict[str, list[BurnOutcome]] = defaultdict(list)
    for outcome in unique_outcomes:
        outcomes_by_id[outcome.burn_id].append(outcome)
    matches: list[dict[str, Any]] = []
    for burn_id, plan_parts in plans_by_id.items():
        history = outcomes_by_id.get(burn_id, [])
        if not history:
            continue
        plan = plan_parts[0]
        planned = sum(item.planned_hectares for item in plan_parts)
        treated = sum(item.treated_hectares for item in history)
        latest = max(
            (item.start for item in history if item.start is not None),
            default=None,
        )
        matches.append(
            {
                "burn_id": burn_id,
                "name": plan.name,
                "jfmp_year": plan.jfmp_year,
                "treatment_type": plan.treatment_type,
                "planned_hectares": planned,
                "treated_hectares": treated,
                "treated_to_planned_ratio": treated / planned,
                "plan_part_count": len(plan_parts),
                "history_record_count": len(history),
                "latest_start": latest.isoformat() if latest else None,
            }
        )
    matched_planned = sum(item["planned_hectares"] for item in matches)
    matched_treated = sum(item["treated_hectares"] for item in matches)
    cost_per_hectare = direct_cost_aud / statewide_treated_hectares
    examples = sorted(
        matches,
        key=lambda item: item["latest_start"] or "",
        reverse=True,
    )[:10]
    return {
        "evidence_status": "verified-official-public-records",
        "plan_feature_count": len(plan_rows),
        "unique_plan_record_count": len(unique_plans),
        "plan_unit_count": len(plans_by_id),
        "history_feature_count": len(outcome_rows),
        "unique_history_record_count": len(unique_outcomes),
        "history_burn_id_count": len(outcomes_by_id),
        "matched_burn_unit_count": len(matches),
        "matched_planned_hectares": matched_planned,
        "matched_treated_hectares": matched_treated,
        "aggregate_treated_to_planned_ratio": (
            matched_treated / matched_planned if matched_planned else None
        ),
        "matched_examples": examples,
        "economic_proxy": {
            "statewide_direct_planned_burn_cost_aud_2024_25": direct_cost_aud,
            "statewide_planned_burn_treated_hectares_2024_25": statewide_treated_hectares,
            "aggregate_direct_cost_aud_per_treated_hectare": cost_per_hectare,
            "matched_area_direct_cost_proxy_aud": matched_treated * cost_per_hectare,
            "source": RISK_MITIGATION_REPORT_URL,
            "interpretation": (
                "statewide aggregate direct-cost benchmark applied to matched treated area; "
                "not an observed burn-unit cost, saving or return on investment"
            ),
        },
        "crew_scenarios": {
            "official_public_guidance_personnel": [20, 30, 70],
            "shift_hours_scenario": 12,
            "person_hours_per_operation": [240, 360, 840],
            "source": CREW_GUIDANCE_URL,
            "interpretation": (
                "resource scenarios from official public ranges; not actual crew rosters"
            ),
        },
        "constraints": [
            "identifier alignment is not polygon overlap or causal attribution",
            "a staged burn may treat only part of the displayed planned polygon",
            "treated area is an official historical outcome, not a safety result",
            "economic and crew values are transparent planning proxies, not realised records",
        ],
    }


def build_spatial_delivery_summary(
    planned_geojson: dict[str, Any],
    outcome_geojson: dict[str, Any],
) -> dict[str, Any]:
    """Measure plan/outcome polygon overlap in Australian Albers (EPSG:3577)."""

    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform, unary_union

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3577", always_xy=True)

    def group(payload: dict[str, Any], key: str) -> dict[str, list[object]]:
        grouped: dict[str, list[object]] = defaultdict(list)
        for feature in payload.get("features", []):
            properties = feature.get("properties", {})
            burn_id = properties.get(key)
            geometry = feature.get("geometry")
            if burn_id and geometry:
                projected = transform(transformer.transform, shape(geometry))
                if not projected.is_valid:
                    projected = projected.buffer(0)
                if not projected.is_empty:
                    grouped[str(burn_id).strip()].append(projected)
        return grouped

    plans = group(planned_geojson, "TREAT_NO")
    outcomes = group(outcome_geojson, "FIRE_NO")
    rows: list[dict[str, Any]] = []
    for burn_id in sorted(set(plans) & set(outcomes)):
        plan = unary_union(plans[burn_id])
        outcome = unary_union(outcomes[burn_id])
        overlap = plan.intersection(outcome)
        union = plan.union(outcome)
        planned_ha = plan.area / 10_000.0
        treated_ha = outcome.area / 10_000.0
        overlap_ha = overlap.area / 10_000.0
        rows.append(
            {
                "burn_id": burn_id,
                "planned_polygon_hectares": planned_ha,
                "treated_polygon_hectares": treated_ha,
                "intersection_hectares": overlap_ha,
                "plan_area_covered": overlap_ha / planned_ha if planned_ha else None,
                "treated_area_inside_plan": overlap_ha / treated_ha if treated_ha else None,
                "intersection_over_union": overlap.area / union.area if union.area else None,
            }
        )
    total_planned = sum(item["planned_polygon_hectares"] for item in rows)
    total_treated = sum(item["treated_polygon_hectares"] for item in rows)
    total_overlap = sum(item["intersection_hectares"] for item in rows)
    return {
        "crs": "EPSG:3577 Australian Albers",
        "matched_burn_unit_count": len(rows),
        "planned_polygon_hectares": total_planned,
        "treated_polygon_hectares": total_treated,
        "intersection_hectares": total_overlap,
        "aggregate_plan_area_covered": total_overlap / total_planned if total_planned else None,
        "aggregate_treated_area_inside_plan": (
            total_overlap / total_treated if total_treated else None
        ),
        "per_burn": rows,
        "interpretation": (
            "official polygon intersection for identifier-matched records; descriptive historical "
            "delivery evidence, not causal risk reduction or operational safety validation"
        ),
    }


def fetch_matched_delivery_geometries(
    burn_ids: Iterable[str],
    *,
    transport: Callable[[str], dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ids = sorted({item.strip() for item in burn_ids if item.strip()})
    if not ids:
        empty = {"type": "FeatureCollection", "features": []}
        return empty, empty, {"plans": {}, "outcomes": {}}
    quoted = ",".join(f"'{item.replace(chr(39), chr(39) * 2)}'" for item in ids)
    plans, plan_provenance = fetch_arcgis_geojson(
        PLANNED_BURNS_URL,
        where=f"TREAT_NO IN ({quoted})",
        out_fields=["TREAT_NO", "TREAT_NAME", "HECTARES"],
        transport=transport,
    )
    outcomes, outcome_provenance = fetch_arcgis_geojson(
        FIRE_HISTORY_URL,
        where=f"FIRETYPE='Burn' AND FIRE_NO IN ({quoted})",
        out_fields=["FIRE_NO", "NAME", "AREA_HA", "START_DATE"],
        transport=transport,
    )
    return plans, outcomes, {"plans": plan_provenance, "outcomes": outcome_provenance}
