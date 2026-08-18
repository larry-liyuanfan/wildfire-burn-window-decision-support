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

mkdir -p "${PROJECT_ROOT}/logs" "$(dirname "${IMAGE_PATH}")"
cd "${PROJECT_ROOT}"
apptainer build --fakeroot "${IMAGE_PATH}" spartan/Apptainer.def

