#!/bin/bash
#SBATCH --job-name=burn-full
#SBATCH --account=punim2936
#SBATCH --array=1972-2024%6
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
module load GCCcore/13.3.0 Apptainer/1.4.5

: "${PROJECT_ROOT:?Repository must live on project GPFS}"
: "${IMAGE_PATH:?Point to the reviewed Apptainer image}"
: "${PRESCRIPTIONS_PATH:?Point to the private FMS workbook outside Git}"
: "${VICCLIM_ROOT:?Set the confirmed compute-visible VicClim6 path; no macOS default}"
: "${BURN_CLASS:?Set one exact BurnClass value after supervisor confirmation}"
: "${OUTPUT_ROOT:?Use project GPFS, not home}"

YEAR="${SLURM_ARRAY_TASK_ID}"
RUN_DIR="${OUTPUT_ROOT}/${BURN_CLASS// /_}/${YEAR}"
mkdir -p "${PROJECT_ROOT}/logs" "${RUN_DIR}"

# Every array item is restartable: a completed metrics file is its checkpoint.
if [[ -s "${RUN_DIR}/metrics.json" ]]; then
  echo "checkpoint exists: ${RUN_DIR}/metrics.json"
  exit 0
fi

cd "${PROJECT_ROOT}"
srun apptainer exec \
  --bind "${VICCLIM_ROOT}:${VICCLIM_ROOT}:ro,${PRESCRIPTIONS_PATH}:${PRESCRIPTIONS_PATH}:ro,${OUTPUT_ROOT}:${OUTPUT_ROOT}" \
  "${IMAGE_PATH}" \
  python scripts/run_with_dask.py \
    --workers 8 --threads-per-worker 1 --memory-limit 7GiB -- \
    analyse \
    --prescriptions "${PRESCRIPTIONS_PATH}" \
    --input "${VICCLIM_ROOT}" \
    --backend netcdf \
    --chunks '{"time":168,"lat":64,"lon":64}' \
    --burn-class "${BURN_CLASS}" \
    --start "${YEAR}-01-01" --end "${YEAR}-12-31T23:59:59" \
    --durations 2 4 6 \
    --missing-policy error \
    --data-kind real \
    --output-dir "${RUN_DIR}"
