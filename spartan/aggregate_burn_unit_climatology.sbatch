#!/bin/bash
#SBATCH --job-name=flare-burn-id-aggregate
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:10:00
#SBATCH --output=/data/gpfs/projects/punim1257/Group44/outputs/flare-burn-id-climatology-20260903/logs/%x-%j.out
#SBATCH --error=/data/gpfs/projects/punim1257/Group44/outputs/flare-burn-id-climatology-20260903/logs/%x-%j.err

set -euo pipefail

readonly EXPECTED_OUTPUT_ROOT=/data/gpfs/projects/punim1257/Group44/outputs/flare-burn-id-climatology-20260903
: "${OUTPUT_ROOT:=${EXPECTED_OUTPUT_ROOT}}"
: "${PROJECT_ROOT:=${OUTPUT_ROOT}/repo}"
: "${FLARE_PYTHON:=${OUTPUT_ROOT}/.venv/bin/python}"
: "${FLARE_GIT_SHA:?Pin the pushed commit to execute}"
[[ "${OUTPUT_ROOT}" == "${EXPECTED_OUTPUT_ROOT}" ]] || exit 2
[[ -x "${FLARE_PYTHON}" ]] || exit 2
[[ "$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_SHA}" ]] || exit 2

module purge
module load "${FLARE_TOOLCHAIN_MODULE:-GCCcore/11.3.0}"
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"
export PYTHONUNBUFFERED=1 PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"
mkdir -p "${OUTPUT_ROOT}/aggregate"
cd "${PROJECT_ROOT}"
srun "${FLARE_PYTHON}" -m burnwindows.cli aggregate-burn-unit-climatology \
  --input "${OUTPUT_ROOT}/annual" --year-start 1973 --year-end 2023 \
  --expected-burn-units 176 --output "${OUTPUT_ROOT}/aggregate/compact.json" \
  --failure-output "${OUTPUT_ROOT}/aggregate/quality_failure.json"
