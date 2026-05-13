# Wildfire Burn-window Decision Support

This project documents a prescribed-burn decision support workflow for identifying safe and operationally useful burn windows in Victoria, Australia.

The work combines gridded climate data with expert-defined fire management prescriptions. The repository is prepared as a sanitized portfolio version and includes project documentation, summary results, and analysis outputs that can be shared safely.

## Problem

Prescribed burning needs suitable weather and fuel conditions. A burn window is only available when multiple constraints are satisfied at the same time, such as temperature, humidity, wind, and drought conditions.

This project turns multi-dimensional climate data and expert thresholds into a rule-based burn suitability analysis workflow.

## Data

| Source | Description |
|---|---|
| VicClim6 | NetCDF climate data for Victoria |
| Coverage | 1972-2024 |
| Spatial resolution | About 4 km grid |
| Temporal resolution | Hourly climate variables |
| Variables | Temperature, relative humidity, wind speed, FFDI, KBDI, drought factor |
| FMS prescriptions | Expert-defined burn suitability thresholds |

## Method

The analysis workflow includes:

1. Load multi-variable NetCDF climate files with Xarray.
2. Align variables across time, latitude, and longitude.
3. Convert daily KBDI data to hourly resolution for rule alignment.
4. Apply expert threshold rules to generate burn-window masks.
5. Analyze monthly and hourly burn-window patterns.
6. Diagnose limiting factors when burn windows are unavailable.
7. Run threshold sensitivity analysis for temperature ranges.

## 2024 Demo Results

| Result | Value |
|---|---:|
| All conditions OK | 6.49% |
| Temperature OK | 37.53% |
| Relative humidity OK | 24.61% |
| Wind OK | 72.44% |
| KBDI OK | 38.64% |

Monthly burn-window frequency was highest in March, April, November, and December in the 2024 demo.

| Month | Mean burn-window frequency |
|---:|---:|
| 3 | 14.52% |
| 4 | 11.20% |
| 11 | 10.88% |
| 12 | 10.56% |

Hour-of-day analysis showed stronger burn-window availability in the early morning. In the 2024 demo, the highest average hourly frequencies occurred around 00:00-03:00.

## Sensitivity Analysis

Temperature threshold sensitivity:

| Temperature range | Mean burn-window frequency |
|---|---:|
| 12-28 | 9.04% |
| 15-25 | 6.49% |
| 18-24 | 4.02% |

Relaxing the temperature range from 15-25 to 12-28 increased the average burn-window frequency from 6.49% to 9.04% in the 2024 demo.

## Limiting Factors

The analysis also identifies why windows fail. In the 2024 demo:

| Factor | Outside-range frequency |
|---|---:|
| Relative humidity | 75.39% |
| Temperature | 62.47% |
| KBDI | 61.36% |
| Wind | 27.56% |

This helps separate weather constraints that are usually binding from those that are less restrictive.

## Tech Stack

Python, Xarray, Dask, Pandas, NumPy, Matplotlib, NetCDF, geospatial climate data.

## Notes

This repository is a sanitized portfolio version. Raw climate datasets, internal project documents, and restricted materials are not redistributed.