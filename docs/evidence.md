# Evidence ledger

## Current claims

| Claim | Status | Reproduction evidence | Public-use rule |
|---|---|---|---|
| Package exposes five deterministic typed tools | `verified-local` | Source plus passing tests | May describe implementation and test coverage |
| Rule compiler covers all 43 workbook rows | `verified-local-private-input` | `burn-window inspect` summary; workbook stays private | May state row coverage, not reproduce thresholds |
| Bounds, seasons, missing data and unresolved values are explicit | `verified-local` | Unit/golden tests | May describe behavior |
| Daily-to-hourly alignment prevents default same-day lookahead | `verified-local` | Alignment tests | May describe behavior and assumption |
| Continuous 2/4/6-hour windows handle irregular time gaps | `verified-local` | Window tests | May describe behavior |
| Dask and NumPy agree on deterministic fixtures | `verified-synthetic` | Test and benchmark artifacts | Say fixture/synthetic; do not imply full-data performance |
| Binary optimizer returns feasible schedules and compares two greedies | `verified-synthetic` | Optimizer tests | Say tested on golden scenarios |
| Nominal tool reports deterministic rejection blockers and a discrete crew-capacity frontier | `verified-synthetic` | Optimizer/tool tests | Describe as local decision diagnostics; never call the delta an LP shadow price, causal effect or money |
| Max-min and CVaR MILPs remain feasible across 30 seeded suites | `verified-synthetic` | `decision-benchmark`; 49 tests | Say synthetic operations benchmark only |
| Nominal MILP mean lift over best greedy is 1.79% (bootstrap mean 95% interval 0.91%–2.77%) | `verified-synthetic` | 30 seeds; 6,000 held-out scenarios/policy | Do not call this financial return or real-data lift |
| Robust policy mean mobilisation penalty is 2.55% below nominal MILP | `verified-synthetic` | Same deterministic benchmark | Units are scenario penalty, not dollars; do not imply field savings |
| Robust P05 lift over nominal is stable | `unsupported` | Bootstrap interval crosses zero | Do not claim robustness improvement |
| CVaR mean held-out P05 lift over nominal is 1.42% (paired-seed bootstrap mean 95% interval 0.25%–3.25%) | `verified-synthetic` | 30 seeds; 40 independent planning scenarios/run; 6,000 held-out scenarios/policy | State that 60% of runs selected the same policy; do not call it financial, real-data or universal improvement |
| Nominal, max-min and CVaR schedules expose independent feasibility/objective certificates plus HiGHS MIP proof metadata | `verified-local` | Optimizer tests, including a deliberately tampered schedule | Feasibility certificate is not itself an optimality proof; MIP gap/bound apply to the solver run |
| 2024 suitability was 6.49%; widened temperature gave 9.04% | `project-record-only` | No accessible data/run manifest | Must not be called reproduced or verified |
| One year contains about 317M space-time points; East Gippsland 140M samples | `project-record-only` | Shape calculation and filter log absent | Do not use publicly until reproduced |
| 1972–2024 full pipeline completes and is restartable | `code-ready/data-blocked` | Slurm/Apptainer scripts exist; no Spartan job artifact | Describe architecture, not completed computation |
| Group44 VicClim6 GPFS source path | `verified-path/access-blocked` | `/data/gpfs/projects/punim1257/Group44/data/raw/VicClim6` and canonical 2020 temperature file supplied by the team; read-only checks from `yzhang3504` return permission denied because its observed groups omit `punim1257` | May state that the source was located; must not claim file inventory, successful open or analysis until ACL is granted and a run artifact exists |
| Group44 code on Spartan | `verified-code-checkout` | Private repository commit `8724a295` cloned without transferring credentials to `/data/gpfs/projects/punim2936/portfolio_20260818/Group44-2026-capstone-project`; clean `main` checkout; temporary Git bundle removed | Proves code availability only; does not imply VicClim6 ACL, runtime installation or a real-data run |
| Official VicClim6 public-source inventory | `verified-metadata-only` | VicClim6 descriptor: hourly 4 x 4 km NetCDF, January 1972–June 2024; official Viewer rechecked 21 Aug and requires login/account registration before product access | May describe source discovery and access boundary; not a real-data pipeline run |
| Anonymous public ARCO-ERA5 read/derive/write preflight | `verified-real-public-reanalysis` | Spartan job 29461166; exact commit `9f2401f8`; 24 x 23 x 41 slice; output and metrics hashes in `artifacts/public/arco_era5_preflight_29461166.json`; 49 local tests | May describe real public-data engineering and provenance only; 0.25-degree ERA5 is not VicClim6 and proves no FFDI/KBDI, prescription, window, trend or economic result |
| 168-hour public weather-only necessary-condition screen | `verified-real-public-reanalysis` | Spartan job `29462231`, commit `51db417`: 23 x 41 grid, 158,424 cell-hours, 43,690 passes, 2/4/6-hour run counts 7,642/4,798/2,937, metrics/manifest hashes in `artifacts/public/arco_era5_weather_screen_29462231.json` | Call this a historical weather-only upper bound; missing FFDI/FFFI/rain/fuel/site/burn-plan constraints prohibit burn-window, safety, area or economic claims |
| Full-year 2024 public weather-only screen | `verified-real-public-reanalysis` | Spartan job `29462409`, commit `51db417`: 8,784 x 23 x 41 = 8,283,312 cell-hours; 1,391,401 passes (16.7976%); 2/4/6-hour run counts 243,967/160,691/96,270; exit 0:0, elapsed 2:59:47, MaxRSS 1,077,252 KiB; compact record `artifacts/public/arco_era5_weather_screen_2024_29462409.json` | Scale/provenance evidence only; same missing constraints prohibit burn-window, safety, area, risk or economic claims |
| Chunked public weather-screen checkpoint/restart | `verified-real-public-reanalysis` | 49 local tests plus Spartan job `29467567`, exact commit `6eb8c5f`: controlled exit 75 at 168/336 hours, resumed from 168 hours, exact semantic SHA `6e13387b...205a` vs uninterrupted baseline over 316,848 cell-hours; exit 0:0, elapsed 16:38, MaxRSS 763,468 KiB; compact record `artifacts/public/arco_era5_restart_gate_29467567.json` | Proves this bounded public weather-screen restart path only; not every failure mode, VicClim6, burn suitability, safety, area or economic value |
| 1→4 worker efficiency ≥60% | `target` | No same-workload real-data runs | Do not state as result |
| Optimizer improves objective ≥10% over best greedy | `not-met-synthetic` | Observed mean lift 1.79% on the current suite | Do not state ≥10%; use the measured result and boundary |

## Required artifact bundle for a verified real-data metric

Each result directory must contain:

- `run_manifest.json`: git SHA, inputs/data version, configuration, hardware,
  Slurm IDs and `data_kind=real`;
- `metrics.json`: metric definition, numerator, denominator, duration rule,
  missing-data policy and warnings;
- `error_cases.json`: failed or excluded cases;
- source log and job exit status;
- no raw restricted data or credentials.

Before promotion into a resume, record the exact artifact path and personal
contribution in the career evidence ledger. A screenshot or manually copied
percentage is insufficient.

## Local source provenance reviewed

- `W1-2_Larry/Scope_and_Threshold_Confirmation.md` (prepared 5 Aug 2026);
- `W1-2_Larry/inspect_project_data.py` and its local smoke-test record;
- private `FMS-Prescriptions_2.xlsx` (43 rows, 25 columns; content not copied);
- `04_项目证据/FLARE野火项目.md` (historical career-asset boundary).

## Publication checklist

- run secret and PII scanners;
- confirm no workbook, NetCDF, shapefile, reference JSON or internal document is tracked;
- keep Kerchunk source paths out of public artifacts;
- retain `project-record-only` language for historical metrics;
- obtain data-owner approval before publishing derived geographic outputs;
- do not add an open-source licence until code and source-data rights are clear.

