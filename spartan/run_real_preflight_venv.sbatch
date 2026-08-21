#!/bin/bash
#SBATCH --job-name=burn-preflight-venv
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

set -euo pipefail
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"

: "${PROJECT_ROOT:?Set the Group44 or portfolio repository checkout}"
: "${FLARE_PYTHON:?Set the registered FLARE environment Python executable}"
: "${VICCLIM_ROOT:?Set the confirmed Group44 VicClim6 root}"
: "${OUTPUT_ROOT:?Use approved Group44/project output storage}"

SAMPLE_FILE="${VICCLIM_ROOT}/WRFV6_TSFC1972-2024/2020/01/IDV71000_VIC_T_SFC.nc"
[[ -x "${FLARE_PYTHON}" ]] || { echo "FLARE Python is not executable: ${FLARE_PYTHON}" >&2; exit 2; }
[[ -r "${SAMPLE_FILE}" ]] || { echo "Canonical Group44 sample is not readable: ${SAMPLE_FILE}" >&2; exit 2; }
[[ -d "${PROJECT_ROOT}/src/burnwindows" ]] || { echo "burnwindows package source is missing" >&2; exit 2; }
mkdir -p "${PROJECT_ROOT}/logs" "${OUTPUT_ROOT}"

cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"
srun "${FLARE_PYTHON}" - <<'PY'
import sys

import dask
import h5netcdf
import numpy
import pandas
import xarray

print(
    {
        "python": sys.executable,
        "numpy": numpy.__version__,
        "pandas": pandas.__version__,
        "xarray": xarray.__version__,
        "dask": dask.__version__,
        "h5netcdf": h5netcdf.__version__,
    }
)
PY
srun "${FLARE_PYTHON}" -c \
  'from burnwindows.cli import main; raise SystemExit(main())' \
  inventory \
  --input "${VICCLIM_ROOT}" \
  --sample-count 3 \
  --output-dir "${OUTPUT_ROOT}/inventory-${SLURM_JOB_ID}"
