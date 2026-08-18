# Interview defence map

## 90-second story

The project converts expert prescribed-burning constraints into deterministic,
Agent-callable tools over multi-decadal gridded climate data. I built a typed
rule compiler that preserves inequality boundaries and records ambiguous fields
instead of guessing, a no-lookahead daily-to-hourly alignment policy, Xarray/Dask
evaluation with NetCDF/Zarr/Kerchunk adapters, continuous-window extraction,
limiting-factor and sensitivity tools, and a binary scheduling layer validated
against greedy baselines. Tests currently verify the engineering behavior on
golden synthetic fixtures. Full VicClim6 metrics remain pending a recorded
Spartan run, so historical 6.49% and 9.04% values are not claimed as reproduced.

## Code evidence map

| Interview question | Evidence |
|---|---|
| How do you stop an Agent from inventing domain rules? | `models.py`, `rules.py`, `tools.py` |
| How do you prevent temporal leakage? | `alignment.py` and alignment tests |
| How are strict/inclusive boundaries handled? | `parse_threshold`, `evaluate_condition`, rule tests |
| What happens when a variable is missing? | explicit `MissingPolicy` and warning envelope |
| How is a continuous operational window defined? | `extract_windows`; irregular gaps split runs |
| How do you scale beyond memory? | `io.py`, Kerchunk builder and Spartan Slurm array |
| How do you know optimisation output is valid? | MILP constraints plus independent `validate_selection` |
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

