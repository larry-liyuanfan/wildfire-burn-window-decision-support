"""Fetch one official FFMVic district polygon with a pinned, auditable query."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

SERVICE = "https://spatial.planning.vic.gov.au/gis/rest/services/boundary/MapServer/12/query"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--district", default="MURRAY GOLDFIELDS")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--max-allowable-offset",
        type=float,
        default=0.001,
        help="simplification tolerance in EPSG:4326 degrees; default is well below the 4 km grid",
    )
    args = parser.parse_args()
    if args.max_allowable_offset <= 0 or args.max_allowable_offset > 0.005:
        raise ValueError("max-allowable-offset must be in (0, 0.005]")
    district_sql = args.district.replace("'", "''")
    params = {
        "where": f"DISTRICT_NAME='{district_sql}'",
        "outFields": "DISTRICT_NAME,REGION_NAME",
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": f"{args.max_allowable_offset:.6f}",
        "geometryPrecision": "6",
        "f": "geojson",
    }
    url = f"{SERVICE}?{urlencode(params)}"
    with urlopen(url, timeout=60) as response:
        payload = json.load(response)
    features = payload.get("features", [])
    if len(features) != 1:
        raise RuntimeError(f"official query returned {len(features)} features, expected one")
    properties = features[0].get("properties", {})
    if properties.get("DISTRICT_NAME") != args.district:
        raise RuntimeError("official query returned an unexpected district")
    payload["_provenance"] = {
        "source_service": SERVICE,
        "source_layer": "Land and Fire District Major",
        "query_url": url,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_crs": "EPSG:4326",
        "max_allowable_offset_degrees": args.max_allowable_offset,
        "license": "Creative Commons Attribution 4.0 International",
        "attribution": "State of Victoria (Department of Energy, Environment and Climate Action)",
    }
    serialised = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(serialised, encoding="utf-8")
    digest = hashlib.sha256(serialised.encode("utf-8")).hexdigest()
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "bytes": len(serialised.encode("utf-8")),
                "sha256": digest,
                "district": properties.get("DISTRICT_NAME"),
                "region": properties.get("REGION_NAME"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
