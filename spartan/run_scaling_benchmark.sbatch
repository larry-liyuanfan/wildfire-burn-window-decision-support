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

: "${PROJECT_ROOT:?Set repository path on project GPFS}"
: "${IMAGE_PATH:?Set reviewed Apptainer image path}"
: "${OUTPUT_ROOT:?Set project-storage output root}"

WORKERS=(1 2 4)
N="${WORKERS[$SLURM_ARRAY_TASK_ID]}"
OUT="${OUTPUT_ROOT}/synthetic-scaling/workers-${N}"
mkdir -p "${PROJECT_ROOT}/logs" "${OUT}"
cd "${PROJECT_ROOT}"

srun apptainer exec "${IMAGE_PATH}" \
  python scripts/run_with_dask.py \
    --workers "${N}" --threads-per-worker 1 --memory-limit 7GiB -- \
    benchmark --hours 8760 --cells 4096 \
    --chunk-hours 168 --chunk-cells 256 \
    --scheduler distributed --seed 20260818 --output-dir "${OUT}"

