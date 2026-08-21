# Paper-to-hiring map

This document links research ideas to implemented code, measured evidence and
explicit non-claims. A citation is not presented as an implementation unless the
corresponding code and test/artifact are named below.

## 1. Threshold sensitivity is a first-class result

Clarke et al. (2019) found prescribed-burning opportunity estimates to be highly
sensitive to the chosen weather definition, not just to the climate input. That
motivates this repository's typed rule AST, explicit unresolved values and
`compare_threshold_scenarios` tool instead of one hard-coded Boolean mask.

- Paper: H. Clarke et al., *Climate change effects on the frequency,
  seasonality and interannual variability of suitable prescribed burning
  weather conditions in south-eastern Australia*, Agricultural and Forest
  Meteorology 271 (2019),
  <https://doi.org/10.1016/j.agrformet.2019.03.005>.
- Code: `src/burnwindows/rules.py`, `src/burnwindows/tools.py`.
- Evidence: 43 workbook rows compile into typed or explicitly unresolved
  fields; boundary and threshold-scenario tests are part of the 59-test suite.
- Hiring signal: converts policy spreadsheets into versionable, testable domain
  logic and makes sensitivity auditable.
- Boundary: workbook thresholds remain private, and no public-data weather pass
  is labelled an operational burn window.

## 2. Spatiotemporal changes require regional and seasonal diagnostics

Di Virgilio et al. (2020) showed that mitigation opportunities can shift by
location and month rather than moving uniformly. The project therefore exposes
region trends and limiting-factor attribution instead of reporting one statewide
average.

- Paper: G. Di Virgilio et al., *Climate Change Significantly Alters Future
  Wildfire Mitigation Opportunities in Southeastern Australia*, Geophysical
  Research Letters 47 (2020), <https://doi.org/10.1029/2020GL088893>.
- Code: `src/burnwindows/trend.py`, `src/burnwindows/engine.py`,
  `src/burnwindows/tools.py`.
- Evidence: deterministic fixtures cover trend grouping, continuous-window
  extraction and limiting factors. The official-district 51-year array
  `29486334` and aggregate `29486336` completed 51/51 years and produced a
  Theil–Sen pass-rate change of +0.331 percentage points/decade with a seeded
  five-year moving-block-bootstrap 95% interval of +0.012 to +0.613.
- Hiring signal: turns a large climate cube into explainable regional decision
  features rather than a single descriptive statistic.
- Boundary: the completed trend is descriptive for the six mapped conditions,
  one workbook class and the official Murray Goldfields district grid-centre
  mask. It is not causal attribution, a complete prescription, a burn-unit
  result or operational availability.

## 3. Tail-risk scheduling should remain a solvable, auditable programme

Rockafellar and Uryasev's classic CVaR formulation converts empirical tail risk
into a linear optimisation form. The implementation combines binary candidate
selection and capacity constraints with an empirical lower-tail CVaR objective,
then evaluates the fixed selection on separately seeded held-out scenarios.

- Paper: R. T. Rockafellar and S. Uryasev, *Optimization of Conditional
  Value-at-Risk*, Journal of Risk 2(3) (2000),
  <https://doi.org/10.21314/JOR.2000.038>.
- Code: `src/burnwindows/optimizer.py`,
  `src/burnwindows/decision_benchmark.py`.
- Evidence: independent feasibility/objective certificates; HiGHS MIP
  gap/bound metadata; 30 planning seeds and 6,000 held-out scenario evaluations
  per policy. CVaR improved mean held-out P05 utility by 1.42% versus nominal
  (paired-seed 95% interval 0.25%–3.25%).
- Hiring signal: joins uncertainty-aware optimisation with independent
  verification and honest out-of-sample evaluation.
- Boundary: utility and mobilisation penalties are synthetic scenario units,
  not dollars, hectares treated or fire-risk reduction.

## 4. Cloud-optimised arrays are an engineering control, not a domain result

Google Research's ARCO-ERA5 converts ERA5 into analysis-ready Zarr stores for
selective cloud access. The public-data adapter uses that source to test the
Xarray/Zarr pipeline, checkpointing and provenance without copying the full
climate payload.

- Source and reproduction recipes: Google Research,
  <https://github.com/google-research/arco-era5>.
- Code: `src/burnwindows/public_reanalysis.py`,
  `scripts/evaluate_public_weather_screen.py`.
- Evidence: Spartan job `29462409` evaluated 8,283,312 cell-hours for 2024;
  job `29467567` proved controlled checkpoint/resume semantic equivalence.
- Hiring signal: real cloud-array ingestion, bounded memory, resumability and
  exact data/code provenance on HPC.
- Boundary: ERA5 at 0.25 degrees is not VicClim6 at 4 km, and the three-variable
  screen omits FFDI/FFFI, rain history, fuel moisture, site and burn-plan rules.

## 5. Frontier predictive-prescriptive work is an adjacent direction

Recent work on knowledge-guided prescribed-fire emulation and joint predictive-
prescriptive wildfire resource allocation motivates a future emulator-plus-
schedule gate. This repository currently implements the deterministic rule and
optimisation layer only; it does not claim a learned fire-spread emulator or
suppression-outcome model.

- Knowledge-guided prescribed-fire modelling:
  <https://arxiv.org/abs/2310.01593>.
- Predictive and prescriptive wildfire-suppression optimisation:
  <https://arxiv.org/abs/2605.04510>.
- Promotion requirement: authorised historical outcome data, leakage-safe
  spatiotemporal splits, calibrated uncertainty, a deterministic-rule baseline,
  and held-out decision improvement with a predeclared safety boundary.

## Interview summary

The technical story is not "I processed NetCDF". It is:

1. compile operational prescriptions into typed, testable rules;
2. evaluate large spatiotemporal arrays without lookahead and with restartable
   provenance;
3. expose explanations, sensitivity and typed tools to an Agent;
4. turn candidate windows into a constrained scheduling decision;
5. validate feasibility independently and reject unsupported real-world value
   claims.
