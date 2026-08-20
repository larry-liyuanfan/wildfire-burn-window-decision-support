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
Tests currently verify the engineering behavior on
golden synthetic fixtures. Because authorised VicClim6 access is unavailable,
I also built an anonymous ARCO-ERA5 fallback with explicit source boundaries.
A 168-hour Spartan run processed 158,424 cell-hours and found 43,690 passes of
temperature/RH/wind necessary conditions, with 2/4/6-hour run counts of
7,642/4,798/2,937. Missing FFDI, FFFI, rain history, fuel moisture, site and
burn-plan constraints mean these are not burn windows or safety evidence. A
full 2024 streaming run is in progress, and a separate controlled exit-75 plus
resume gate will compare semantic hashes against an uninterrupted run. Full
VicClim6 metrics remain access-blocked, so historical 6.49% and 9.04% values are
not claimed as reproduced.

## Code evidence map

| Interview question | Evidence |
|---|---|
| How do you stop an Agent from inventing domain rules? | `models.py`, `rules.py`, `tools.py` |
| How do you prevent temporal leakage? | `alignment.py` and alignment tests |
| How are strict/inclusive boundaries handled? | `parse_threshold`, `evaluate_condition`, rule tests |
| What happens when a variable is missing? | explicit `MissingPolicy` and warning envelope |
| How is a continuous operational window defined? | `extract_windows`; irregular gaps split runs |
| How do you scale beyond memory? | `io.py`, Kerchunk builder and Spartan Slurm array |
| What real-data path was actually executed? | `public_reanalysis.py`, `evaluate_public_weather_screen.py`, public run records and Slurm accounting |
| How do you prove restart does not alter results? | checkpoint state plus `compare_public_weather_screen_restart.py`; remote gate remains pending until completed |
| How do you know optimisation output is valid? | MILP constraints plus independent `validate_selection` |
| Why was a candidate rejected, and what would another crew buy? | `explain_selection` plus the typed tool's discrete crew-capacity counterfactuals; both carry non-dual/non-financial boundaries |
| Why CVaR as well as max-min? | `solve_cvar_schedule` exposes a tail-risk parameter and avoids letting one worst scenario dominate |
| What is genuinely measured today? | `docs/evidence.md` and run manifests |

## Expected deep questions

1. Why is a date-labelled daily aggregate delayed by 24 hours?
2. When is forward fill scientifically valid, and what maximum age is safe?
3. Why are seasonal AST leaves neutral outside their active season?
4. How would you resolve overlapping KBDI seasonal rules?
5. Why exclude ground wind instead of deriving it from surface wind?
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

