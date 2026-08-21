#!/bin/bash
#SBATCH --job-name=burn-preflight
#SBATCH --account=punim1257
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail
module load GCCcore/13.3.0 Apptainer/1.4.5

: "${PROJECT_ROOT:?Repository must live on compute-visible storage}"
: "${IMAGE_PATH:?Point to the reviewed Apptainer image}"
: "${VICCLIM_ROOT:?Set the confirmed compute-visible VicClim6 path; no macOS default}"
: "${OUTPUT_ROOT:?Use restricted scratch/project storage, not home}"

[[ -d "${VICCLIM_ROOT}" ]] || { echo "VicClim6 path is not a directory: ${VICCLIM_ROOT}" >&2; exit 2; }
[[ -r "${VICCLIM_ROOT}" ]] || { echo "VicClim6 path is not readable: ${VICCLIM_ROOT}" >&2; exit 2; }
SAMPLE_FILE="${VICCLIM_ROOT}/WRFV6_TSFC1972-2024/2020/01/IDV71000_VIC_T_SFC.nc"
[[ -r "${SAMPLE_FILE}" ]] || { echo "Canonical Group44 sample is not readable: ${SAMPLE_FILE}" >&2; exit 2; }
mkdir -p "${PROJECT_ROOT}/logs" "${OUTPUT_ROOT}"

cd "${PROJECT_ROOT}"
srun apptainer exec \
  --bind "${VICCLIM_ROOT}:${VICCLIM_ROOT}:ro,${OUTPUT_ROOT}:${OUTPUT_ROOT}" \
  "${IMAGE_PATH}" \
  burn-window inventory \
    --input "${VICCLIM_ROOT}" \
    --sample-count 3 \
    --output-dir "${OUTPUT_ROOT}/inventory-${SLURM_JOB_ID}"
