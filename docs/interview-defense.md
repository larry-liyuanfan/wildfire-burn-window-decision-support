# Interview defence map

## 90-second story

The project converts expert prescribed-burning constraints into deterministic,
Agent-callable tools over multi-decadal gridded climate data. I built a typed
rule compiler that preserves inequality boundaries and records ambiguous fields
instead of guessing, a no-lookahead daily-to-hourly alignment policy, Xarray/Dask
evaluation with NetCDF/Zarr/Kerchunk adapters, continuous-window extraction,
limiting-factor and sensitivity tools, and a binary scheduling layer validated
against greedy baselines. I compared nominal, max-min and lower-tail CVaR
formulations, keeping planning scenarios independent from held-out evaluation.
Seventy-nine local tests verify the engineering behavior on golden fixtures. I
also built an anonymous ARCO-ERA5 preflight with explicit source boundaries,
then used an authorised team identity to inventory and process the restricted
VicClim6 collection without copying its payloads.
A full-year 2024 Spartan run processed 8,283,312 cell-hours and found 1,391,401
passes of temperature/RH/wind necessary conditions (16.7976%), with 2/4/6-hour
run counts of 243,967/160,691/96,270. Missing FFDI, FFFI, rain history, fuel
moisture, site and burn-plan constraints mean these are not burn windows or
safety evidence. The controlled exit-75 plus resume job `29467567` stopped at
168/336 hours, restored its checkpoint, and matched the uninterrupted summary
exactly over 316,848 cell-hours (semantic SHA `6e13387b...205a`). This verifies
one bounded restart path, not recovery from every infrastructure failure. The
real 2020 VicClim6 pilot evaluated 317,207,808 statewide space-time cells. The
completed statewide 1973–2023 chain then evaluated 16,142,930,688 cells with
51/51 exact-SHA annual checkpoints and a strict aggregation gate. The data
directory had no regional mask, so I fetched and hashed the official
Murray Goldfields fire-management-district polygon and made spatial scope part
of the aggregation contract. Exact-SHA jobs `29486334`/`29486336` then completed
51/51 years over 992,840,304 regional cells. Six mapped conditions retained
48,143,687 cells (4.8491%), and annual tasks took 44–81 seconds with less than
0.85 GiB MaxRSS. Two fuel/ground-wind conditions remain unmapped, and the
district is not a burn-unit/treatable-area mask. It is therefore a provisional
weather-exposure screen, not a burn approval, complete prescription, safety,
area, risk or economic result. A block-bootstrap descriptive trend is also
non-causal; historical 6.49% and 9.04% values remain unverified.
The district retained 6.1503% of statewide cells while summed elapsed time and
peak RSS fell 83.74% and 88.10%. Per-cell throughput fell to 37.82% of the
statewide rate, which makes fixed I/O/alignment overhead visible. Because the
two chains use different spatial contracts and Git SHAs, I present this as an
observed scope comparison, not worker scaling or causal code acceleration.
I then ran a same-workload 1/2/4-thread gate over 19,509,264 real
region-cell-hours. Outputs were identical, but four-thread efficiency was only
29.78%, so I rejected the pre-registered 60% scaling claim. A second exact-SHA
51-year district chain evaluated seven threshold scenarios. It reproduced the
4.8491% baseline; narrowing/widening all mapped bounds changed the rate to
0.3853%/13.0361%. Paired annual effects use seeded five-year moving-block
bootstrap intervals, and KBDI's 51/51-year zero response is reported as an
inactive bound under this contract—not as general domain irrelevance. These
results are descriptive sensitivity evidence, not causal, safety or economic
evidence.
I then closed two previously missing engineering loops without hiding their
uncertainty. A sixth typed tool derives dry-fuel FMC from the Viney and Van
Wagner--Pickett equations and converts 10-m wind through an explicit reduction
factor; rain-affected hours fail rather than receiving an invented value. An
official FFMVic adapter paginates and hashes 221 JFMP plan features and 430 Fire
History features. It resolves 176/187 burn IDs, joins eight shared IDs, unions
multipart geometries and recomputes overlap in Australian Albers: 422.16 ha of
plan polygons, 162.56 ha of treatment polygons and 161.89 ha intersection.
Public staffing ranges and AUD 288.73/ha statewide direct-cost scale are exposed
as scenarios, not actual rosters, savings or ROI.
Spartan job `29504538` then executed those two proxy variables on real 2020
VicClim6 data: all 8/8 compiled conditions over 19,509,264 district cell-hours,
with a 2.4693% retained rate and 193,450/36,245/7,622 2/4/6-hour endpoints. The
artifact explicitly records that precipitation was unavailable, so the rain
guard was not applied and this remains a proxy evaluation rather than safety
validation.

## Code evidence map

| Interview question | Evidence |
|---|---|
| How do you stop an Agent from inventing domain rules? | `models.py`, `rules.py`, `tools.py` |
| How do you prevent temporal leakage? | `alignment.py` and alignment tests |
| How are strict/inclusive boundaries handled? | `parse_threshold`, `evaluate_condition`, rule tests |
| What happens when a variable is missing? | explicit `MissingPolicy` and warning envelope |
| How is a continuous operational window defined? | `extract_windows`; irregular gaps split runs |
| How do you scale beyond memory? | `io.py`, Kerchunk builder and Spartan Slurm array |
| What real-data path was actually executed? | `io.py`, `spatial.py`, `evaluate_vicclim6_year.py`, the compact VicClim6 inventory/2020, 51-year statewide and 51-year district records plus Slurm accounting; `public_reanalysis.py` remains an independently reproducible public preflight |
| How is regional scope prevented from being mixed across years? | `spatial.py`, region hash/properties in every manifest, and `aggregate_vicclim6_years` single-spatial-contract gate |
| Why did a 93.85% cell reduction produce only an 83.74% elapsed reduction? | `performance.py`, `compare_spatial_scopes.py` and the compact scope-comparison artifact; discuss fixed I/O/alignment overhead and the non-causal comparison boundary |
| Why did four workers fail the scaling gate? | `compare_real_scaling.py`, the 1/2/4 run manifests and `vicclim6_murray_goldfields_worker_scaling_20260822.json`; distinguish identical-result verification from speedup and report 29.78% efficiency as a negative gate |
| How is threshold sensitivity made robust to one unusual year? | `sensitivity.py`, `trend.py`, `aggregate_vicclim6_years.py` and the 51-year redacted record; paired annual effects plus seeded five-year moving-block-bootstrap intervals |
| Why can KBDI show exactly zero sensitivity? | the fixed baseline/scenario contract and per-year effect record; explain an inactive bound conditional on the other mapped constraints without claiming KBDI is generally irrelevant |
| How do you prove restart does not alter results? | local property tests plus remote job `29467567`: controlled exit 75 at 168/336 hours, resume from checkpoint and exact semantic hash match against an uninterrupted 316,848-cell-hour run |
| How do you know optimisation output is valid? | MILP constraints plus independent `validate_selection` |
| Why was a candidate rejected, and what would another crew buy? | `explain_selection` plus the typed tool's discrete crew-capacity counterfactuals; both carry non-dual/non-financial boundaries |
| Why CVaR as well as max-min? | `solve_cvar_schedule` exposes a tail-risk parameter and avoids letting one worst scenario dominate |
| What is genuinely measured today? | `docs/evidence.md` and run manifests |
| How did you move from a district to real burn units? | `official_burns.py`, official ArcGIS attribute/GeoJSON hashes and the public delivery artifact; exact-ID join plus EPSG:3577 union/intersection |
| How are FMC and ground wind now handled? | `fuel_inputs.py` and `derive_fuel_inputs`; two-model FMC interval, rain guard, explicit WRF and `observed_on_site=false` |
| Where do crew and cost numbers come from? | FFMVic public 20/30/70-person scenarios and 2024–25 direct planned-burning cost/area; both remain proxies rather than unit records |

## Expected deep questions

1. Why is a date-labelled daily aggregate delayed by 24 hours?
2. When is forward fill scientifically valid, and what maximum age is safe?
3. Why are seasonal AST leaves neutral outside their active season?
4. How would you resolve overlapping KBDI seasonal rules?
5. Why is a wind-reduction factor a scenario rather than a site measurement?
6. What is lost when only window endpoints are counted in a full grid run?
7. How would chunk shape change for time-series versus map queries?
8. What does Kerchunk virtualise, and what access risks remain?
9. Why compare an exact solver with two greedy baselines?
10. What does the scheduling objective measure, and why is it not money?
11. How would you add spatial crew travel constraints?
12. How would you validate suitability against realised burns without treating unburned windows as negative labels?
13. Which fields remain unresolved in the FMS workbook and why?
14. How can Dask produce correct results but poor performance?
15. What evidence is needed before claiming a worker-scaling result?
16. How do retries/checkpoints avoid double-counting annual outputs?
17. What deterministic outputs should an LLM be allowed to summarise?
18. How are raw data licences separated from code publication?
19. What would make a sensitivity result operationally actionable?
20. Why do historical percentages remain unverified even if they appear in an earlier presentation?
21. How does the CVaR linearisation work, and why are planning and held-out scenarios separately seeded?
22. Why can a positive mean P05 lift coexist with 60% unchanged policies?
23. Why is the discrete crew-capacity objective delta not a shadow price?
24. When can a local blocking-set explanation disagree with a globally optimal counterfactual?
25. Why is the ERA5 pass rate a necessary-condition upper bound rather than a burn-window rate?
26. Which state must cross a chunk boundary so 2/4/6-hour runs are not double-counted or split?
27. Why compare semantic payload hashes instead of raw JSON file hashes after resume?
28. What additional evidence is required before feeding public-weather candidates into a real scheduling or economic claim?
29. Why is an official fire-management district still not a burn-unit or treatable-area mask?
30. How do you interpret a positive Theil–Sen slope whose block-bootstrap interval excludes zero without making a causal claim?
31. Why did masking 6.15% of grid centres reduce annual runtime and MaxRSS, and which operations still scale with time rather than space?
32. Why is the statewide-vs-district comparison not a 1→4 worker benchmark or an Amdahl serial-fraction estimate?
33. Why is the one-worker run the denominator for parallel efficiency, and why does identical output not prove useful scaling?
34. Why use a moving-block bootstrap for annual threshold effects instead of an IID bootstrap?
35. How would you distinguish a genuinely inactive KBDI bound from a unit-conversion or scenario-wiring bug?
36. Why are the all-mapped wider/narrower effects not the sum of the one-factor effects?
37. Why do you union duplicate/multipart plan polygons before computing area?
38. Why can historical treated geometry lie almost entirely inside a current plan while covering only 38% of it?
39. Why is AUD/ha an expenditure-scale proxy rather than a savings estimate?
40. What held-out field data would be needed to calibrate the FMC ensemble and WRF?

