#!/bin/bash
#SBATCH --job-name=burn-image
#SBATCH --account=punim2936
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err
set -euo pipefail

: "${PROJECT_ROOT:?Set PROJECT_ROOT to the cloned repository path on project storage}"
: "${IMAGE_PATH:?Set IMAGE_PATH to a writable project-storage .sif path}"

ARTIFACT_ROOT="$(dirname "${IMAGE_PATH}")"
mkdir -p "${PROJECT_ROOT}/logs" "${ARTIFACT_ROOT}" \
  "${ARTIFACT_ROOT}/apptainer-cache" "${ARTIFACT_ROOT}/apptainer-tmp"
export APPTAINER_CACHEDIR="${ARTIFACT_ROOT}/apptainer-cache"
export APPTAINER_TMPDIR="${ARTIFACT_ROOT}/apptainer-tmp"
module load GCCcore/13.3.0 Apptainer/1.4.5
cd "${PROJECT_ROOT}"
apptainer build --fakeroot "${IMAGE_PATH}" spartan/Apptainer.def
