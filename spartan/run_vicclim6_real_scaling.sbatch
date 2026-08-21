#!/bin/bash
#SBATCH --job-name=vicclim6-real-scale
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --array=0-2%1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err

set -euo pipefail
module load "${FLARE_TOOLCHAIN_MODULE:-GCCcore/11.3.0}"
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
: "${REGION_GEOJSON:?Set the exact official district GeoJSON}"
: "${OUTPUT_ROOT:?Use approved Group44 project output storage}"

WORKER_COUNTS=(1 2 4)
DASK_WORKERS="${WORKER_COUNTS[$SLURM_ARRAY_TASK_ID]}"
YEAR="${BENCHMARK_YEAR:-2020}"
LOAD_START="$(${FLARE_PYTHON} - "${YEAR}" <<'PY'
import sys
from datetime import datetime, timedelta
year = int(sys.argv[1])
print((datetime(year, 1, 1) - timedelta(hours=5)).isoformat())
PY
)"
METRIC_START="${YEAR}-01-01T00:00:00"
END_TIME="${YEAR}-12-31T23:00:00"
RUN_DIR="${OUTPUT_ROOT}/workers-${DASK_WORKERS}"

[[ -x "${FLARE_PYTHON}" ]] || { echo "FLARE Python is not executable" >&2; exit 2; }
[[ -r "${PRESCRIPTIONS}" ]] || { echo "FMS workbook is not readable" >&2; exit 2; }
[[ -r "${REGION_GEOJSON}" ]] || { echo "region GeoJSON is not readable" >&2; exit 2; }
[[ "$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_SHA}" ]] || {
  echo "checkout does not match FLARE_GIT_SHA" >&2
  exit 2
}
if [[ -s "${RUN_DIR}/metrics.json" && -s "${RUN_DIR}/run_manifest.json" ]]; then
  echo "checkpoint exists: ${RUN_DIR}"
  exit 0
fi

SENSITIVITY_ARGS=()
if [[ -n "${THRESHOLD_SCENARIOS:-}" ]]; then
  [[ -r "${THRESHOLD_SCENARIOS}" ]] || {
    echo "threshold scenario JSON is not readable" >&2
    exit 2
  }
  SENSITIVITY_ARGS=(--threshold-scenarios "${THRESHOLD_SCENARIOS}")
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
  --burn-class "${BURN_CLASS:-Murray Goldfields - Box ironbark forest}" \
  --start "${LOAD_START}" \
  --end "${END_TIME}" \
  --metric-start "${METRIC_START}" \
  --metric-end "${END_TIME}" \
  --chunks '{"time":168,"latitude":37,"longitude":61}' \
  --scheduler threads \
  --dask-workers "${DASK_WORKERS}" \
  --durations 2 4 6 \
  --missing-policy error \
  --data-kind real \
  --region-geojson "${REGION_GEOJSON}" \
  --region-label "${REGION_LABEL:-Murray Goldfields FFMVic district}" \
  "${SENSITIVITY_ARGS[@]}" \
  --output-dir "${RUN_DIR}"
