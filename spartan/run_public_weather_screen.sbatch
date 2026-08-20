#!/bin/bash
#SBATCH --job-name=flare-weather-screen
#SBATCH --partition=cascade
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:25:00
#SBATCH --output=/data/gpfs/projects/punim2936/portfolio_20260818/flare-artifacts/logs/%x-%j.out
set -euo pipefail

: "${FLARE_GIT_COMMIT:?set the exact pushed commit to execute}"
FLARE_REMOTE_URL="${FLARE_REMOTE_URL:-https://github.com/larry-liyuanfan/wildfire-burn-window-decision-support.git}"
CODE_ROOT="${SLURM_TMPDIR:-/tmp}/flare-code-${SLURM_JOB_ID:?}"
OUTPUT_DIR="${OUTPUT_DIR:-/data/gpfs/projects/punim2936/portfolio_20260818/flare-artifacts/weather-screen-${FLARE_GIT_COMMIT:0:7}}"
START="${START:-2024-03-01T00:00:00}"
HOURS="${HOURS:-168}"
CHUNK_HOURS="${CHUNK_HOURS:-168}"
VENV="${SLURM_TMPDIR:-/tmp}/flare-screen-venv-${SLURM_JOB_ID:?}"
export PIP_CACHE_DIR="${SLURM_TMPDIR:-/tmp}/pip-cache-${SLURM_JOB_ID:?}"
trap 'rm -rf -- "${VENV}" "${PIP_CACHE_DIR}" "${CODE_ROOT}"' EXIT

git clone --filter=blob:none --no-checkout "${FLARE_REMOTE_URL}" "${CODE_ROOT}"
git -C "${CODE_ROOT}" checkout --detach "${FLARE_GIT_COMMIT}"
[[ "$(git -C "${CODE_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_COMMIT}" ]]
cd "${CODE_ROOT}"
module purge
module load GCCcore/11.3.0
module load Python/3.11.3
python -m venv "${VENV}"
"${VENV}/bin/python" -m pip install -e '.[public-data]'
RESUME_ARGS=()
if [[ "${RESUME:-0}" == "1" ]]; then
  RESUME_ARGS+=(--resume)
fi
/usr/bin/time -v "${VENV}/bin/python" scripts/evaluate_public_weather_screen.py \
  --output "${OUTPUT_DIR}" \
  --start "${START}" \
  --hours "${HOURS}" \
  --chunk-hours "${CHUNK_HOURS}" \
  "${RESUME_ARGS[@]}"
