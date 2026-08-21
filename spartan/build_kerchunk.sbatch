#!/bin/bash
#SBATCH --job-name=burn-ref
#SBATCH --account=punim2936
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
module load GCCcore/13.3.0 Apptainer/1.4.5

: "${PROJECT_ROOT:?Set repository path on project GPFS}"
: "${IMAGE_PATH:?Set reviewed Apptainer image path}"
: "${VICCLIM_ROOT:?Set the confirmed compute-visible VicClim6 path; no macOS default}"
: "${REFERENCE_PATH:?Keep references on restricted project storage until paths are reviewed}"

mkdir -p "${PROJECT_ROOT}/logs" "$(dirname "${REFERENCE_PATH}")"
cd "${PROJECT_ROOT}"
srun apptainer exec --bind "${VICCLIM_ROOT}:${VICCLIM_ROOT}:ro" "${IMAGE_PATH}" \
  python scripts/build_kerchunk.py \
    --input-glob "${VICCLIM_ROOT}/**/*.nc" \
    --output "${REFERENCE_PATH}"
