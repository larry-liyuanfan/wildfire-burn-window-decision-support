# Data-access runbook

## Confirmed Group44 Spartan layout (21 August 2026)

The team-provided compute-visible source is no longer an unknown Mediaflux
mount. The authoritative paths are:

```text
Git checkout:  /home/<Spartan user>/Group44-2026-capstone-project
Shared root:   /data/gpfs/projects/punim1257/Group44
VicClim6 root: /data/gpfs/projects/punim1257/Group44/data/raw/VicClim6
Sample file:   .../WRFV6_TSFC1972-2024/2020/01/IDV71000_VIC_T_SFC.nc
```

The current automated SSH identity is `yzhang3504`, whose observed group list
contains `punim2936` but not `punim1257`. Read-only `stat`, `find` and sample-file
checks against the Group44 path all returned `Permission denied`. The private
GitHub team repository is reachable with write permission, but cloning code
cannot grant GPFS data access. No raw file was copied, no alternate identity was
guessed and no credential was read.

The minimum external fix is therefore one of:

1. add `yzhang3504` to the `punim1257`/Group44 ACL; or
2. provide the already-authorised Spartan username as a separate SSH host.

After that single access change, run the exact read-only gate below. Do not
download or duplicate the collection into home or `punim2936`.

```bash
VICCLIM_ROOT=/data/gpfs/projects/punim1257/Group44/data/raw/VicClim6
SAMPLE="$VICCLIM_ROOT/WRFV6_TSFC1972-2024/2020/01/IDV71000_VIC_T_SFC.nc"
id
test -r "$SAMPLE"
python - <<'PY'
import xarray as xr
from pathlib import Path

path = Path("/data/gpfs/projects/punim1257/Group44/data/raw/VicClim6/WRFV6_TSFC1972-2024/2020/01/IDV71000_VIC_T_SFC.nc")
with xr.open_dataset(path, decode_times=False) as dataset:
    print({"sizes": dict(dataset.sizes), "variables": sorted(dataset.data_vars)})
PY
```

This is an access preflight, not a real-data result. The first compute job must
still inventory files, bytes, time coverage, variables, units and calendar
before applying any burn rule.

## Observed through 21 August 2026

- The local project materials contain the FMS workbook and Week 1–2 documents.
- No `.nc`, `.nc4` or Zarr input was found in the local project/search paths.
- The workbook opens successfully and contains 43 burn-class rows and 25 columns.
- Spartan Open OnDemand login was verified as `yzhang3504`; the `punim2936`
  account and `/data/gpfs/projects/punim2936` project storage are accessible.
- The team later supplied the authoritative `punim1257/Group44` GPFS path. It
  exists but is inaccessible to the current `yzhang3504` SSH identity because
  that identity is not a member of `punim1257`.
- Spartan provides both `unimelb-mf-clients` (credential-config based) and
  `mediaflux-data-mover` (shareable-token based). Neither a client config nor a
  shareable token was present in the SSH environment. The currently logged-in
  Open OnDemand account had no active Virtual Desktop session to reuse.
- A second official route was checked rather than assuming Mediaflux was the
  only source. The public [VicClim Viewer](https://vicclim-next.dri.edu/) and its
  [VicClim6 description](https://vicclim-next.dri.edu/Victoria_gridded_climatology_description_Version_6_0.pdf)
  confirm hourly 4 x 4 km NetCDF coverage from January 1972 through **June
  2024**. The viewer advertises bounded CSV/chart exports, but its product API
  rejected an unauthenticated request because a session ID is required. No
  public bulk-NetCDF URL was discovered, and no external account was created on
  the candidate's behalf.
- A browser-level recheck on 21 August reached the official Viewer directly.
  The home page displayed `Login required`; the registration page requires an
  account name, email address, first name, last name, password and password
  confirmation. Supplying those personal fields and creating the external
  account is therefore an explicit user-authorisation step, not an automated
  data-download fallback. No form fields were filled or submitted.
- `/data/gpfs/projects/punim2936` had only about 2.5 GiB free, so the full
  collection must not be copied there blindly. First inventory collection size,
  then select restricted scratch or another approved compute-visible location.
- An earlier team record says one real January 1972 temperature file opened as
  744 hourly timestamps on a 148 x 244 grid. That record has no retained file
  hash or run artifact and is therefore **project-record-only**, not a reproduced
  result.

This is an access-state statement, not evidence that the source dataset is
unavailable to the research team.

## Anonymous public engineering fallback

The official Google Research ARCO-ERA5 store provides anonymous hourly
0.25-degree reanalysis. It is not a substitute for VicClim6, but it can validate
the storage, Xarray and physical-unit derivation path while Mediaflux access is
unavailable. Spartan job `29461166`, exact commit `9f2401f8`, read 1 February
2024 00:00--23:00 UTC over 34--39.5 degrees south and 140.5--150.5 degrees east.
The slice contained 24 x 23 x 41 cells and produced temperature, relative
humidity, wind speed and precipitation fields. The 835,744-byte derived NetCDF
hash is `d0e769f5c772bf30543c0a77acfb8329c7aeea3cb8a6cfa2d6e843bd12528fe7`;
job elapsed time was 97 seconds and batch MaxRSS was 768,868 KiB.

The source collection and NetCDF remain on Spartan. The public compact manifest
records the source URL, store, time/space selection, dimensions and hashes. No
FFDI, KBDI, prescription rule, burn-window rate, trend or economic metric is
derived from this fallback.

The viewer can become a bounded validation fallback after an authorised account
session is available: export a small region/time slice, retain its URL/query and
hash, and compare it with the NetCDF pipeline's golden output. It is **not** a
verified substitute for full-corpus Mediaflux access and must not be described
as a 1972--2024 Spartan run.

## First Spartan session

Run these read-only checks before submitting even the preflight:

```bash
PROJECT=/data/gpfs/projects/punim1257/Group44
VICCLIM="$PROJECT/data/raw/VicClim6"

id
sacctmgr show assoc where user="$USER" format=Account,Partition,QOS
find "$VICCLIM" -maxdepth 2 -type f -name '*.nc' | head
du -sh "$VICCLIM"
df -h "$(dirname "$VICCLIM")"
```

The old `/Volumes/...` value is a macOS Mediaflux mount and must not be used on
Spartan. Run
`burn-window inventory` to record file count, bytes, a metadata fingerprint and
the first/middle/last NetCDF headers without copying payload data. Then submit
`spartan/run_real_preflight.sbatch`; run `sbatch --test-only` before the real
submission. Do not copy raw data into Git, OneDrive or home storage.

## Preconditions for the 1972–2024 array

1. Confirm `yzhang3504` (or a separately configured authorised SSH identity)
   can read the Group44 sample file.
2. Confirm the `punim1257` account, default partition/QOS and project storage quota.
3. Confirm NetCDF variable names, dimensions, time coverage, calendar and units.
4. Obtain written decisions for window duration, wind semantics, KBDI seasonal
   labels and missing/unmapped constraints.
5. Build the Apptainer image and run one year/burn class before scaling the array.
6. Store outputs under project GPFS and retain the Slurm job ID in each manifest.
