# Official district boundary

The regional run uses the Victorian Government `boundary` ArcGIS service,
layer 12 (`Land and Fire District Major`, source dataset `LF_DISTRICT`). The
fetch script requires an exact `DISTRICT_NAME` match, requests EPSG:4326 and
fails unless the service returns exactly one feature.

Source metadata:

- catalogue: <https://discover.data.vic.gov.au/dataset/delwp-land-and-fire-district-boundaries>
- REST service: <https://spatial.planning.vic.gov.au/gis/rest/services/boundary/MapServer/12>
- licence: Creative Commons Attribution 4.0 International
- attribution: State of Victoria (Department of Energy, Environment and
  Climate Action)

The default `maxAllowableOffset=0.001` degree simplification is below the
VicClim6 grid spacing (about 0.036 degrees). Membership is evaluated at each
grid-cell centre with an even-odd polygon test. The GeoJSON query URL,
retrieval timestamp, tolerance and licence are embedded as provenance. The
run manifest separately hashes the exact downloaded boundary.

```bash
python scripts/fetch_ffmvic_district.py \
  --district "MURRAY GOLDFIELDS" \
  --output "$OUTPUT_ROOT/boundaries/murray-goldfields.geojson"
```

This district mask improves spatial attribution but does not supply burn-unit
polygons, land-tenure eligibility, access constraints or treatable area. It
therefore supports a district-level weather exposure screen, not a burn plan
or operational approval.
