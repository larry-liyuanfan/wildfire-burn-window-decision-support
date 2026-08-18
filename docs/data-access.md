# Data-access runbook

## Observed on 18 August 2026

- The local project materials contain the FMS workbook and Week 1–2 documents.
- No `.nc`, `.nc4` or Zarr input was found in the local project/search paths.
- The workbook opens successfully and contains 43 burn-class rows and 25 columns.
- Spartan Open OnDemand login was verified as `yzhang3504`; the `punim2936`
  account and `/data/gpfs/projects/punim2936` project storage are accessible.
- A read-only search of the accessible project tree and the user's home did not
  locate VicClim6 or another FLARE NetCDF source. The documented Mediaflux path
  still needs to be mounted or mapped to a compute-visible path.

This is an access-state statement, not evidence that the source dataset is
unavailable to the research team.

## First Spartan session

Run these read-only checks before submitting the full array:

```bash
PROJECT=/Volumes/proj-6600_prescribed_burn_windows-1128.4.1443
VICCLIM="$PROJECT/data/climate/VicClim6"

id
sacctmgr show assoc where user="$USER" format=Account,Partition,QOS
find "$VICCLIM" -maxdepth 2 -type f -name '*.nc' | head
du -sh "$VICCLIM"
```

Then run `burn-window inspect` against one read-only NetCDF file and save stdout,
module/Apptainer version, data path, dimensions, variables, time range and
missing counts. Do not copy raw data into Git, OneDrive or home storage.

## Preconditions for the 1972–2024 array

1. Confirm the actual compute-visible VicClim6 path; the documented `/Volumes/...`
   path may be a Mediaflux mount that differs between login and compute nodes.
2. Confirm the `punim2936` account, default partition/QOS and project storage quota.
3. Confirm NetCDF variable names, dimensions, time coverage, calendar and units.
4. Obtain written decisions for window duration, wind semantics, KBDI seasonal
   labels and missing/unmapped constraints.
5. Build the Apptainer image and run one year/burn class before scaling the array.
6. Store outputs under project GPFS and retain the Slurm job ID in each manifest.
