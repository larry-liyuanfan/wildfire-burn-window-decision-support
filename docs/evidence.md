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
| 2024 suitability was 6.49%; widened temperature gave 9.04% | `project-record-only` | No accessible data/run manifest | Must not be called reproduced or verified |
| One year contains about 317M space-time points; East Gippsland 140M samples | `project-record-only` | Shape calculation and filter log absent | Do not use publicly until reproduced |
| 1972–2024 full pipeline completes and is restartable | `code-ready/data-blocked` | Slurm/Apptainer scripts exist; no Spartan job artifact | Describe architecture, not completed computation |
| 1→4 worker efficiency ≥60% | `target` | No same-workload real-data runs | Do not state as result |
| Optimizer improves objective ≥10% over best greedy | `target` | No agreed real candidate set | Do not state as result |

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

