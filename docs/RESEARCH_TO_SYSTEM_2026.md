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
- Still required for a field-value claim: burn-unit polygons, parcel priority and
  history, calibrated forecast error, crew/cost records and realised burn
  decisions. Current optimiser results therefore remain synthetic utility units,
  not dollars, hectares treated or risk reduction.

## 3. Fuel moisture cannot be manufactured from weather fields

A 2026 Victorian study reports a seven-day spatial dead-fuel-moisture forecasting
system trained on 23,354 site-days from 27 forest sites, with day-1/day-7 median
RMSE of 11.5%/12.8%. Its observation data and trained models are not publicly
redistributable. This is direct evidence that the missing surface-fuel-moisture
constraint needs labelled, below-canopy observations and cannot be replaced by
an undocumented temperature/RH proxy.

- Source: [Keeble et al., *Environmental Modelling & Software* 200, 106942](https://doi.org/10.1016/j.envsoft.2026.106942)
- Current decision: keep `FMCSurfaceInside` unmapped and fail visibly at the
  prescription-completeness gate.
- Safe extension point: add a versioned `FuelMoistureProvider` only after a
  licensed model/observation feed is available; evaluate it with spatially held
  out sites and time-rolling splits before allowing it into the rule AST.

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

The authorised data area does not contain a region polygon or burn-unit mask.
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

This is the current technical contribution. The next scientifically meaningful
upgrade is not a larger neural network; it is the licensed fuel-moisture,
ground-wind and burn-unit evidence needed to close the prescription and outcome
loops.
