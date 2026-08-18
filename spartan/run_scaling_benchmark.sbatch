#!/bin/bash
#SBATCH --job-name=burn-scale
#SBATCH --account=punim2936
#SBATCH --array=0-2
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:45:00
#SBATCH --output=logs/%x-%A_%a.out
#SBATCH --error=logs/%x-%A_%a.err
set -euo pipefail
module load GCCcore/13.3.0 Apptainer/1.4.5

: "${PROJECT_ROOT:?Set repository path on project GPFS}"
: "${IMAGE_PATH:?Set reviewed Apptainer image path}"
: "${OUTPUT_ROOT:?Set project-storage output root}"

BENCHMARK_HOURS="${BENCHMARK_HOURS:-8760}"
BENCHMARK_CELLS="${BENCHMARK_CELLS:-4096}"

WORKERS=(1 2 4)
N="${WORKERS[$SLURM_ARRAY_TASK_ID]}"
OUT="${OUTPUT_ROOT}/synthetic-scaling/workers-${N}"
mkdir -p "${PROJECT_ROOT}/logs" "${OUT}"
cd "${PROJECT_ROOT}"

srun apptainer exec --bind "${OUTPUT_ROOT}:${OUTPUT_ROOT}" "${IMAGE_PATH}" \
  python scripts/run_with_dask.py \
    --workers "${N}" --threads-per-worker 1 --memory-limit 7GiB -- \
    benchmark --hours "${BENCHMARK_HOURS}" --cells "${BENCHMARK_CELLS}" \
    --chunk-hours 168 --chunk-cells 256 \
    --scheduler distributed --seed 20260818 --output-dir "${OUT}"
