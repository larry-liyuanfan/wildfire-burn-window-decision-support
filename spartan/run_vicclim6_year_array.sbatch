#!/bin/bash
#SBATCH --job-name=vicclim6-year
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --array=1973-2023%4
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err

set -euo pipefail
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

: "${PROJECT_ROOT:?Set the exact FLARE repository checkout}"
: "${FLARE_GIT_SHA:?Pin the pushed commit to execute}"
: "${FLARE_PYTHON:?Set the FLARE environment Python executable}"
: "${VICCLIM_ROOT:?Set the Group44 VicClim6 root}"
: "${PRESCRIPTIONS:?Set the restricted FMS workbook path}"
: "${OUTPUT_ROOT:?Use approved Group44 project output storage}"

BURN_CLASS="${BURN_CLASS:-Murray Goldfields - Box ironbark forest}"
YEAR="${SLURM_ARRAY_TASK_ID}"
METRIC_START="${YEAR}-01-01T00:00:00"
LOAD_START="$(${FLARE_PYTHON} - "${YEAR}" <<'PY'
import sys
from datetime import datetime, timedelta
year = int(sys.argv[1])
if year == 1973:
    # December 1972 is absent. Exclude the first 24 hours instead of
    # forward-filling unavailable KBDI/drought-factor observations.
    print("1973-01-02T00:00:00")
else:
    print((datetime(year, 1, 1) - timedelta(hours=5)).isoformat())
PY
)"
if [[ "${YEAR}" == "1973" ]]; then
  METRIC_START="1973-01-02T00:00:00"
fi
END_TIME="${YEAR}-12-31T23:00:00"
RUN_DIR="${OUTPUT_ROOT}/vicclim6-year-${SLURM_ARRAY_JOB_ID}_${YEAR}"

[[ -x "${FLARE_PYTHON}" ]] || { echo "FLARE Python is not executable" >&2; exit 2; }
[[ -r "${PRESCRIPTIONS}" ]] || { echo "FMS workbook is not readable" >&2; exit 2; }
[[ "$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_SHA}" ]] || {
  echo "checkout does not match FLARE_GIT_SHA" >&2
  exit 2
}
if [[ -s "${RUN_DIR}/metrics.json" && -s "${RUN_DIR}/run_manifest.json" ]]; then
  echo "checkpoint exists: ${RUN_DIR}"
  exit 0
fi

mkdir -p "${PROJECT_ROOT}/logs" "${OUTPUT_ROOT}"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

srun "${FLARE_PYTHON}" -c \
  'from burnwindows.cli import main; raise SystemExit(main())' \
  analyse \
  --backend vicclim6 \
  --input "${VICCLIM_ROOT}" \
  --prescriptions "${PRESCRIPTIONS}" \
  --burn-class "${BURN_CLASS}" \
  --start "${LOAD_START}" \
  --end "${END_TIME}" \
  --metric-start "${METRIC_START}" \
  --metric-end "${END_TIME}" \
  --chunks '{"time":168,"latitude":37,"longitude":61}' \
  --scheduler synchronous \
  --dask-workers 1 \
  --durations 2 4 6 \
  --missing-policy error \
  --data-kind real \
  --output-dir "${RUN_DIR}"
