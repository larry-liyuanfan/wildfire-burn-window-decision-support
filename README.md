# Wildfire Burn-window Decision Support

Deterministic domain tools that turn gridded fire-weather data and expert
prescriptions into auditable candidate windows, explanations, sensitivity
scenarios and feasible schedules. The project is designed as a **trusted tool
layer for an AI agent**: an LLM may choose a tool, but it cannot invent weather
rules, bypass missing-data policy or return an infeasible schedule.

## Why this project exists

The research question is how often suitable prescribed-burning conditions occur
in Victoria, how availability changes across space and time, and how sensitive
the result is to the definition of a window. The engineering question is how to
make that analysis reproducible at VicClim6 scale (1972–2024, approximately
4 km) and safe to call from an Agentic AI application.

This repository complements a multimodal-search/Agent portfolio by demonstrating
the part that must remain deterministic: typed tools, explicit constraints,
large-array execution, provenance and refusal to guess unresolved semantics.

## Stable tool contracts

All five public tools return a `ToolEnvelope` containing status, data version,
source, active constraints, warnings and a typed result.

| Tool | Deterministic responsibility |
|---|---|
| `find_burn_windows` | Evaluate an AND-rule and extract continuous 2/4/6-hour runs |
| `explain_limiting_factors` | Attribute all and exclusive rule failures |
| `compare_threshold_scenarios` | Compare explicit threshold perturbations with a fixed baseline |
| `get_region_trend` | Report Theil–Sen slope and seeded block-bootstrap interval |
| `optimize_burn_schedule` | Compare two greedy baselines with a validated binary programme, machine-checkable feasibility/solver certificates, local rejection reasons and discrete crew-capacity counterfactuals |

The Pydantic schemas are in `src/burnwindows/models.py`; JSON Schema can be
generated directly with `ToolEnvelope.model_json_schema()` and the request
models used by a calling service.

## Technical design

- **Rule AST:** every usable workbook value becomes a typed bound; anything not
  safely interpretable is retained in `unresolved`, never silently dropped.
- **Time alignment:** date-labelled daily data defaults to a 24-hour availability
  lag and backward-only fill. Using a value earlier requires an explicit source
  guarantee that its timestamp is its availability time. Naive timestamps require
  an explicit source timezone; ambiguous or nonexistent DST wall times fail.
- **Units:** conversion occurs only when NetCDF attributes explicitly declare
  Kelvin, fractional humidity or metres/second. Unknown units produce warnings.
- **Missing data:** callers choose `error`, `fail` or `ignore`; the default is
  `error`. Unmapped fuel/ground-wind constraints are excluded with warnings
  unless the caller explicitly includes them.
- **Scale:** Xarray/Dask evaluation stays lazy until metrics are computed.
  NetCDF, Zarr and Kerchunk references share one input adapter.
- **Scheduling:** candidate windows are binary variables with resource and daily
  capacity constraints. The decision layer now compares nominal, max-min and
  lower-tail CVaR formulations; every solver output is independently validated.
  The Agent-facing nominal tool also reports which selected windows block each
  rejected candidate and a one-step crew-capacity frontier. Those diagnostics
  are explicitly not LP duals, causal effects or financial marginal values.

See [architecture](docs/architecture.md), [decision log](docs/decisions.md) and
[evidence ledger](docs/evidence.md).

## Quick start

```bash
python -m venv .venv
python -m pip install -e ".[dev,kerchunk]"
pytest
```

The private prescription workbook remains outside Git:

```bash
burn-window inspect --prescriptions /restricted/FMS-Prescriptions_2.xlsx
```

Create a deterministic **synthetic** smoke-test input:

```bash
python scripts/generate_synthetic_fixture.py --output data/synthetic.nc
burn-window inspect \
  --prescriptions /restricted/FMS-Prescriptions_2.xlsx \
  --input data/synthetic.nc
```

Run one real-data slice only after confirming field semantics and units:

```bash
burn-window analyse \
  --prescriptions /restricted/FMS-Prescriptions_2.xlsx \
  --input /restricted/VicClim6 \
  --burn-class "<exact class name>" \
  --durations 2 4 6 \
  --missing-policy error \
  --data-kind real \
  --output-dir artifacts/run-001
```

Every analysis emits `run_manifest.json`, `metrics.json` and
`error_cases.json`. The manifest captures git SHA, input hashes where practical,
configuration, hardware, Slurm IDs and whether the run used real or synthetic
data.

Run the deterministic operations benchmark:

```bash
burn-window decision-benchmark --repetitions 30 --held-out-scenarios 200 \
  --output-dir artifacts/decision-benchmark
```

The verified synthetic run, refreshed on 2026-08-20, evaluated 30 seeded
candidate sets and 6,000 held-out uncertainty scenarios per policy. CVaR used
40 separately seeded planning scenarios per run, so evaluation scenarios never
entered its objective. All greedy, nominal, max-min and CVaR MILP outputs were
independently feasible. Nominal MILP improved mean
scenario utility over the best greedy by 1.79% (paired-seed bootstrap mean 95%
interval 0.91%–2.77%). Robust MILP reduced mean mobilisation-penalty units by
2.55%, but its held-out P05 utility interval crossed zero relative to nominal
MILP. CVaR improved mean held-out P05 utility by 1.42% versus nominal (paired-seed
bootstrap mean 95% interval 0.25%–3.25%); 60% of runs selected the same policy,
so this is a bounded average tail-utility result rather than universal dominance.
These are synthetic utility units, not dollars, realised area or fire-risk reduction.

Every nominal, max-min and CVaR result now carries two separate audit records:
an independent primal certificate that recomputes the selected objective and
all crew/day constraints, and the HiGHS branch-and-bound proof metadata
(optimality status, relative MIP gap, objective bound and node count). The
former verifies feasibility; only the latter can support an optimality claim.

## Spartan execution

`spartan/` contains an Apptainer definition and restartable Slurm jobs:

- `build_image.sbatch` builds the versioned runtime;
- `run_real_preflight.sbatch` inventories collection scale and three
  representative NetCDF headers in a 15-minute, 2-CPU gate;
- `build_kerchunk.sbatch` creates references without copying climate payloads;
- `run_full_pipeline.sbatch` runs a 1972–2024 array with one checkpoint per year;
- `run_scaling_benchmark.sbatch` compares 1/2/4 workers on a clearly labelled
  deterministic synthetic benchmark.
- `run_arco_era5_preflight.sbatch` reads a bounded Victoria slice from the
  anonymous public ARCO-ERA5 Zarr store and verifies the real-data I/O and
  meteorological-derivation path without copying the source collection.
- `run_public_weather_screen.sbatch` streams the public weather-only screen in
  configurable time chunks. Its JSON checkpoint preserves per-cell unfinished
  run lengths, monthly counts and constraint failures, so 2/4/6-hour runs remain
  exact across chunk and restart boundaries.
- `run_public_weather_restart_gate.sbatch` compares one uninterrupted 336-hour
  public-data run with a controlled exit-75 plus resume run and requires an
  exact semantic hash match. The remote gate remains unverified until its Slurm
  job completes.

Set the required environment variables shown at the top of each script. Raw
climate data, source prescriptions, Kerchunk paths and analysis outputs stay on
restricted project storage.

Spartan job `29461166` completed the public-data preflight from exact commit
`9f2401f8`: 24 hourly steps over a 23 x 41 Victoria grid were read from the
official ARCO-ERA5 store, temperature/RH/wind/precipitation fields were derived,
and an 835,744-byte NetCDF with SHA-256 `d0e769f5...28fe7` was produced in 97
seconds (batch MaxRSS 768,868 KiB). The compact
[run record](artifacts/public/arco_era5_preflight_29461166.json) is public; the
NetCDF remains on Spartan. This is an anonymous 0.25-degree engineering
preflight, **not** VicClim6 validation, an FFDI/KBDI derivation, a burn-window
result or economic evidence.

Spartan job `29462231` then executed the bounded weather-only screen from exact
commit `51db417`: 168 hourly steps over the same 23 × 41 Victoria grid produced
158,424 evaluated cell-hours and 43,690 necessary-condition passes (27.5779%).
The 2/4/6-hour maximal-run counts were 7,642/4,798/2,937; RH, temperature and
wind failure counts were 85,611/51,495/35,344. The job completed in 4 min 49 s
with batch MaxRSS 762,940 KiB. The compact
[run record](artifacts/public/arco_era5_weather_screen_29462231.json) is public.
Missing FFDI, next-day FFDI, FFFI, rain-history, fuel moisture, site and burn-plan
constraints make this an upper-bound weather screen, not a burn-window, safety,
treated-area or economic result. The full 2024 job remains in progress.

## Evidence status

Verified locally in this repository:

- package installation and deterministic tool contracts;
- boundary, missing-value, no-lookahead and irregular-time tests;
- NumPy/Xarray-Dask equivalence on fixtures;
- solver feasibility validation and greedy comparisons;
- deterministic rejection explanations and crew-capacity counterfactuals;
- max-min robust MILP plus a 30-seed/6,000-scenario-per-policy operations benchmark;
- runtime compilation of all 43 workbook rows into typed or unresolved fields.
- 49 local tests plus bounded real public ARCO-ERA5 preflight and 168-hour
  weather-only screen jobs on Spartan with exact commits and hashes.

Not yet verified from accessible real VicClim6 data:

- the prior 2024 values **6.49%** and **9.04%**;
- prior scale, runtime, completeness or speedup claims;
- 1972–2024 trend, 1→4 worker scaling, and real-candidate optimisation value.

These values are historical project records only and must not be presented as
reproduced results until an artifact contains the exact data range, rule version,
commit and hardware.

## Data and publication boundary

This repository does not redistribute the FMS workbook, VicClim6 NetCDF files,
fire-history data, internal documents or raw Kerchunk references. Workbook
thresholds may have licensing constraints, so no generated threshold dump is
committed. The code can be reviewed publicly; project data and derived artifacts
require a separate licensing and privacy review. No open-source licence is
granted at this stage.
