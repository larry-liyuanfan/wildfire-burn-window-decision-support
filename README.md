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
| `optimize_burn_schedule` | Compare earliest/highest-score greedy baselines with a validated binary programme |

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
  capacity constraints. Every solver output is independently validated.

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

## Spartan execution

`spartan/` contains an Apptainer definition and restartable Slurm jobs:

- `build_image.sbatch` builds the versioned runtime;
- `build_kerchunk.sbatch` creates references without copying climate payloads;
- `run_full_pipeline.sbatch` runs a 1972–2024 array with one checkpoint per year;
- `run_scaling_benchmark.sbatch` compares 1/2/4 workers on a clearly labelled
  deterministic synthetic benchmark.

Set the required environment variables shown at the top of each script. Raw
climate data, source prescriptions, Kerchunk paths and analysis outputs stay on
restricted project storage.

## Evidence status

Verified locally in this repository:

- package installation and deterministic tool contracts;
- boundary, missing-value, no-lookahead and irregular-time tests;
- NumPy/Xarray-Dask equivalence on fixtures;
- solver feasibility validation and greedy comparisons;
- runtime compilation of all 43 workbook rows into typed or unresolved fields.

Not yet verified from accessible real VicClim6 data:

- the prior 2024 values **6.49%** and **9.04%**;
- prior scale, runtime, completeness or speedup claims;
- 1972–2024 trend, 1→4 worker scaling, and optimisation lift targets.

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
