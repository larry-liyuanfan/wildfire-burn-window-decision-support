# Data-access runbook

## Observed through 20 August 2026

- The local project materials contain the FMS workbook and Week 1–2 documents.
- No `.nc`, `.nc4` or Zarr input was found in the local project/search paths.
- The workbook opens successfully and contains 43 burn-class rows and 25 columns.
- Spartan Open OnDemand login was verified as `yzhang3504`; the `punim2936`
  account and `/data/gpfs/projects/punim2936` project storage are accessible.
- A read-only search of the accessible project tree and the user's home did not
  locate VicClim6 or another FLARE NetCDF source. The documented Mediaflux path
  still needs to be mounted or mapped to a compute-visible path.
- Spartan provides both `unimelb-mf-clients` (credential-config based) and
  `mediaflux-data-mover` (shareable-token based). Neither a client config nor a
  shareable token was present in the SSH environment. The currently logged-in
  Open OnDemand account had no active Virtual Desktop session to reuse.
- `/data/gpfs/projects/punim2936` had only about 2.5 GiB free, so the full
  collection must not be copied there blindly. First inventory collection size,
  then select restricted scratch or another approved compute-visible location.
- An earlier team record says one real January 1972 temperature file opened as
  744 hourly timestamps on a 148 x 244 grid. That record has no retained file
  hash or run artifact and is therefore **project-record-only**, not a reproduced
  result.

This is an access-state statement, not evidence that the source dataset is
unavailable to the research team.

## First Spartan session

Run these read-only checks before submitting even the preflight:

```bash
PROJECT=/Volumes/proj-6600_prescribed_burn_windows-1128.4.1443
VICCLIM="$PROJECT/data/climate/VicClim6"

id
sacctmgr show assoc where user="$USER" format=Account,Partition,QOS
find "$VICCLIM" -maxdepth 2 -type f -name '*.nc' | head
du -sh "$VICCLIM"
df -h "$(dirname "$VICCLIM")"
```

The `/Volumes/...` value is the documented macOS Mediaflux mount, not a valid
Spartan default. Resolve a compute-visible path explicitly. Run
`burn-window inventory` to record file count, bytes, a metadata fingerprint and
the first/middle/last NetCDF headers without copying payload data. Then submit
`spartan/run_real_preflight.sbatch`; run `sbatch --test-only` before the real
submission. Do not copy raw data into Git, OneDrive or home storage.

## Preconditions for the 1972–2024 array

1. Confirm the actual compute-visible VicClim6 path; the documented `/Volumes/...`
   path may be a Mediaflux mount that differs between login and compute nodes.
2. Confirm the `punim2936` account, default partition/QOS and project storage quota.
3. Confirm NetCDF variable names, dimensions, time coverage, calendar and units.
4. Obtain written decisions for window duration, wind semantics, KBDI seasonal
   labels and missing/unmapped constraints.
5. Build the Apptainer image and run one year/burn class before scaling the array.
6. Store outputs under project GPFS and retain the Slurm job ID in each manifest.
