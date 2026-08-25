#!/bin/bash
#SBATCH --job-name=flare-burn-overlay
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:15:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

set -euo pipefail
module purge
module load "${FLARE_TOOLCHAIN_MODULE:-GCCcore/11.3.0}"
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"

: "${PROJECT_ROOT:?Set the exact FLARE repository checkout}"
: "${FLARE_GIT_SHA:?Pin the pushed commit to execute}"
: "${FLARE_PYTHON:?Set the FLARE environment Python executable}"
: "${GRID_FILE:?Set one representative VicClim6 NetCDF grid file}"
: "${BURN_GEOJSON:?Set the downloaded official FFMVic current-plan GeoJSON}"
: "${OUTPUT_ROOT:?Use approved Group44 project output storage}"

cd "${PROJECT_ROOT}"
test "$(git rev-parse HEAD)" = "${FLARE_GIT_SHA}"
mkdir -p logs "${OUTPUT_ROOT}"

"${FLARE_PYTHON}" -m burnwindows.cli build-burn-unit-overlay \
  --grid "${GRID_FILE}" \
  --geojson "${BURN_GEOJSON}" \
  --output-dir "${OUTPUT_ROOT}"

