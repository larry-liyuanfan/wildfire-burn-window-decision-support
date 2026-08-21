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

An authorised `punim1257` team identity was used on 21 August 2026. Credentials
were entered only into the interactive SSH prompt and were not written to this
repository, an SSH config, a job script or an artifact. Read-only access to the
canonical file and project account was verified before any compute submission.
Raw NetCDF files were not copied to home, GitHub, OneDrive or `punim2936`.

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

The exact-SHA inventory job `29483795` then recorded six variable families,
3,672 NetCDF files and 263,698,792,008 bytes (245.59 GiB). All six families have
612 monthly files and 51 file-backed year directories: **1973–2023**. The
`1972-2024` strings are collection directory labels, not the available year
range in this GPFS copy. Representative DF, RH and wind headers were opened;
the inventory artifact contains no climate payload.

The team guide's `~/flare_env` workflow is supported by
`spartan/run_real_preflight_venv.sbatch`; the Apptainer route remains available
in `spartan/run_real_preflight.sbatch`. On a short interactive compute
allocation, the authorised identity created `flare_env` with Python 3.11.3,
Xarray 2024.11.0, Dask 2024.12.1, netCDF4 1.7.4 and the editable package. Batch
scripts explicitly load `Python/3.11.3`; omitting that module previously caused
the venv interpreter to fail on `libpython3.11.so.1.0` before data access.

The original environment list is sufficient to open a NetCDF notebook, but the
portfolio pipeline also imports Dask and Pydantic. On an interactive compute
node, install the repository once into that same venv with
`python -m pip install -e ".[milp,kerchunk]"`; do not run package installation on
the login node. The preflight deliberately fails if this runtime is incomplete.

Example with an authorised project identity:

```bash
export PROJECT_ROOT="$HOME/Group44-2026-capstone-project"
export FLARE_PYTHON="$HOME/flare_env/bin/python"
export VICCLIM_ROOT=/data/gpfs/projects/punim1257/Group44/data/raw/VicClim6
export OUTPUT_ROOT=/data/gpfs/projects/punim1257/Group44/outputs/preflight
sbatch --test-only spartan/run_real_preflight_venv.sbatch
sbatch spartan/run_real_preflight_venv.sbatch
```

## Observed through 21 August 2026

- The local project materials contain the FMS workbook and Week 1–2 documents.
- No `.nc`, `.nc4` or Zarr input was found in the local project/search paths.
- The workbook opens successfully and contains 43 burn-class rows and 25 columns.
- The authoritative `punim1257/Group44` GPFS path and canonical 2020
  temperature file are readable under an authorised team identity.
- The local GPFS copy contains 1973–2023, not the full public-product date range.
- VicClim6 mixes classic NetCDF and HDF5-era files across years; forcing one
  backend fails. The loader therefore uses automatic backend selection and
  serial file opening inside each annual process.
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
- The 245.59-GiB collection remains in Group44 project storage. Only compact
  JSON results are written; no duplicate corpus is created.
- Group44 storage did not include a district/burn-unit mask. A separate public
  Victorian Government `LF_DISTRICT` ArcGIS service was therefore queried for
  the exact `MURRAY GOLDFIELDS` feature. The fetch/query, geometry
  simplification and grid-centre mask are documented in `boundary-data.md`;
  this is a district reporting scope, not a burn-unit or treatable-area layer.
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

## Preconditions for the 1973–2023 array

1. Confirm the executing identity is an authorised `punim1257` member and can
   read the Group44 sample file.
2. Confirm the `punim1257` account, default partition/QOS and project storage quota.
3. Confirm NetCDF variable names, dimensions, time coverage, calendar and units.
4. Obtain written decisions for window duration, wind semantics, KBDI seasonal
   labels and missing/unmapped constraints.
5. Build the Apptainer image and run one year/burn class before scaling the array.
6. Store outputs under project GPFS and retain the Slurm job ID in each manifest.
7. For a district run, fetch the official boundary to project storage and pin
   its hash; never reuse a statewide annual directory as regional evidence.
