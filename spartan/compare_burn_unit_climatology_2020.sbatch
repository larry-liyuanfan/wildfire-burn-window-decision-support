#!/bin/bash
#SBATCH --job-name=flare-burn-id-compare
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=/data/gpfs/projects/punim1257/Group44/outputs/flare-burn-id-climatology-20260903/logs/%x-%j.out
#SBATCH --error=/data/gpfs/projects/punim1257/Group44/outputs/flare-burn-id-climatology-20260903/logs/%x-%j.err

set -euo pipefail

readonly EXPECTED_OUTPUT_ROOT=/data/gpfs/projects/punim1257/Group44/outputs/flare-burn-id-climatology-20260903
: "${OUTPUT_ROOT:=${EXPECTED_OUTPUT_ROOT}}"
: "${PROJECT_ROOT:=${OUTPUT_ROOT}/repo}"
: "${FLARE_PYTHON:=${OUTPUT_ROOT}/.venv/bin/python}"
: "${VICCLIM_ROOT:=/data/gpfs/projects/punim1257/Group44/data/raw/VicClim6}"
: "${PRESCRIPTIONS:=/data/gpfs/projects/punim1257/Group44/data/raw/FMS-Prescriptions_2.xlsx}"
: "${OVERLAY:=/data/gpfs/projects/punim1257/Group44/outputs/vicclim6-burn-unit-overlay-20260825/result-murray-goldfields/burn_unit_overlay.json}"
: "${FLARE_GIT_SHA:?Pin the pushed commit to execute}"
: "${DATA_SHA256:=a88d53704f0b865585f5e20b68b13732e3175ab3f05175553220d73f30f688ac4}"
: "${RULE_SHA256:=e063ffda8c003b4fb5e9c9506072cbc6edf78364b358acfb84c13f91a22feb1a}"
: "${SPATIAL_SHA256:=ca1fd90e438665937a26f94a38b5d715aa7caa0420e74f1ac87a491bb3c7db85}"
readonly RUN_DIR="${OUTPUT_ROOT}/comparison-2020"

[[ "${OUTPUT_ROOT}" == "${EXPECTED_OUTPUT_ROOT}" ]] || exit 2
[[ -x "${FLARE_PYTHON}" && -s "${OUTPUT_ROOT}/pilot-2020/metrics.json" ]] || exit 2
[[ "$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_SHA}" ]] || exit 2

module purge
module load "${FLARE_TOOLCHAIN_MODULE:-GCCcore/11.3.0}"
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
export PYTHONUNBUFFERED=1 PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"
mkdir -p "${RUN_DIR}"
cd "${PROJECT_ROOT}"
srun "${FLARE_PYTHON}" -m burnwindows.cli compare-burn-unit-climatology-year \
  --input "${VICCLIM_ROOT}" --prescriptions "${PRESCRIPTIONS}" --overlay "${OVERLAY}" \
  --year 2020 --burn-class "Murray Goldfields - Box ironbark forest" \
  --data-sha256 "${DATA_SHA256}" --expected-rule-sha256 "${RULE_SHA256}" \
  --expected-spatial-sha256 "${SPATIAL_SHA256}" --expected-burn-units 176 \
  --expected-weight-rows 351 --scheduler synchronous --dask-workers 1 \
  --chunks '{"time":168,"latitude":37,"longitude":61}' \
  --wind-reduction-factor 0.33 --fmc-rain-guard-mm 0.2 \
  --pilot-dir "${OUTPUT_ROOT}/pilot-2020" --output-dir "${RUN_DIR}"
