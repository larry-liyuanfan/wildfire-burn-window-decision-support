# Research-to-system map (2025–2026)

This note records which recent and classic ideas materially changed the system,
and which attractive ideas were deliberately **not** claimed without the required
observations. It is a design audit, not a literature-review scorecard.

## 1. Fire-weather indices are inputs, not burn approval

The Australian Bureau of Meteorology documents FFDI as a combination of
temperature, relative humidity, wind speed and Drought Factor; Drought Factor is
itself related to accumulated moisture deficit and KBDI. The same official page
also warns that vegetation, terrain and ignition sources affect bushfire
conditions.

- Source: [Bureau of Meteorology — Forest Fire Danger Index](https://www.bom.gov.au/climate/maps/averages/bushfire/)
- System consequence: `open_vicclim6_period` preserves the native hourly FFDI,
  aligns only daily KBDI/DF backward with an explicit 24-hour availability lag,
  and refuses to call a partial weather-rule pass a safe or operational window.
- Evidence consequence: the public metrics use
  `verified-real-partial-prescription-by-this-run`; two unmapped fuel/ground-wind
  constraints remain visible and excluded rather than guessed.

## 2. Operational value needs forecast uncertainty and parcel allocation

Majumder et al. (2025) combine calibrated weather fail-state probabilities with
parcel priorities and a multi-day allocation engine. Their result is a useful
reference architecture because it connects environmental prediction to a
resource-allocation decision rather than stopping at a weather map.

- Source: [Majumder et al., *Ecological Informatics* 85, 102956](https://pubmed.ncbi.nlm.nih.gov/42004859/)
- Implemented now: typed deterministic rules, candidate explanations,
  nominal/max-min/CVaR scheduling, independent feasibility certificates and
  crew-capacity counterfactuals.
- Implemented outcome layer: current official JFMP burn-unit polygons and Fire
  History treatment polygons are joined by official ID and intersected in
  EPSG:3577. Public crew ranges and statewide direct cost/area provide explicit
  resource scenarios. Calibrated forecast error, unit rosters/invoices and
  prospective realised decisions are still required for a field-value claim;
  optimiser results remain scenario utility rather than savings or risk reduction.

## 3. Fuel moisture proxies must remain distinct from field observations

A 2026 Victorian study reports a seven-day spatial dead-fuel-moisture forecasting
system trained on 23,354 site-days from 27 forest sites, with day-1/day-7 median
RMSE of 11.5%/12.8%. Its observation data and trained models are not publicly
redistributable. This is direct evidence that the missing surface-fuel-moisture
constraint needs labelled, below-canopy observations and cannot be replaced by
an undocumented temperature/RH proxy.

- Source: [Keeble et al., *Environmental Modelling & Software* 200, 106942](https://doi.org/10.1016/j.envsoft.2026.106942)
- Implemented proxy path: `derive_fuel_inputs` returns both the Viney empirical
  estimate and Van Wagner--Pickett equilibrium estimate, their midpoint and
  model-spread interval. Rain-affected hours are returned as missing. Fuel-level
  wind is the 10-m open wind multiplied by a caller-visible reduction factor,
  following published Australian fire-behaviour practice.
- System boundary: historical six-condition results remain unchanged. Only an
  explicit `--derive-fuel-proxies` run promotes the two implemented variables to
  provisional, records `observed_on_site=false` and labels the result
  `proxy-complete`. Site-held-out calibration remains necessary before the
  output can be used as operational or safety evidence.

## 4. What the real VicClim6 run proves

The authorised Spartan inventory found six variable families, 3,672 NetCDF files
and 245.59 GiB. File-backed years are 1973–2023 even though directory names say
`1972-2024`. The production path therefore:

1. treats file inventory as authoritative coverage;
2. reads mixed NetCDF3/HDF5-era files without forcing one storage engine;
3. bounds Dask to the Slurm allocation instead of the 128-core physical node;
4. excludes the first 24 hours of 1973 because December 1972 daily state is absent;
5. gives later years five hours of left context so 2/4/6-hour endpoint counts are
   exact at the year boundary;
6. runs every year as an independently restartable exact-SHA task and aggregates
   only a complete, single-commit, single-prescription and single-spatial-contract result set;
7. estimates descriptive annual change with Theil–Sen slope and a seeded
   five-year moving-block residual bootstrap, with no causal interpretation.

The authorised climate data area does not contain a region polygon or burn-unit mask.
The statewide 2020 run is retained as the initial temporal/rule reference. The
same annual contract subsequently completed all 51 file-backed years over
16,142,930,688 statewide space-time cells (jobs `29484660`/`29484661`). That
chain establishes scale, restartability and a descriptive trend only; it does
not turn the Murray Goldfields workbook class into a statewide operational
prescription.
For the regional chain, the system fetches the official Victorian Government
Murray Goldfields fire-management-district feature by exact name, records its
hash/licence/properties, selects 2,221 grid-cell centres and refuses to aggregate
mixed spatial contracts. Jobs `29486334`/`29486336` completed 51/51 years over
992,840,304 regional cells. This is a reproducible district exposure scope, but
the district still does not encode burn units, land tenure, access or treatable
area, so no area/allocation conclusion is drawn.

The public run records also support a bounded performance comparison. The
district retained 6.1503% of statewide evaluated cells, while summed array-task
elapsed time and maximum RSS fell 83.74% and 88.10%. Per-cell throughput fell to
37.82% of the statewide rate, making fixed file-opening, time-alignment and
aggregation work visible. Because the spatial contracts and code SHAs differ,
the comparison is evidence for resource planning and failure analysis only; it
does not identify a causal speedup, an Amdahl serial fraction or worker-scaling
efficiency.

The outcome loop is now independently exercised using public official data:
221 JFMP plan features and 430 Fire History features resolve to 176/187 burn
IDs, with eight exact-ID matches. Their Australian-Albers union/intersection
contains 422.16 ha of current plan geometry, 162.56 ha of historical treatment
geometry and 161.89 ha of overlap. This is real spatial delivery evidence, but
the current JFMP and historical records may represent staged/repeated burns.
The next scientific upgrade is therefore field calibration and prospective
decision evaluation, not simply a larger model or a stronger adjective.
