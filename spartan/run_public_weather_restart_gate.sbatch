#!/bin/bash
#SBATCH --job-name=flare-restart-gate
#SBATCH --partition=sapphire
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=00:35:00
#SBATCH --output=/data/gpfs/projects/punim2936/portfolio_20260818/flare-artifacts/logs/%x-%j.out
set -euo pipefail

: "${FLARE_GIT_COMMIT:?set the exact pushed commit to execute}"
FLARE_REMOTE_URL="${FLARE_REMOTE_URL:-https://github.com/larry-liyuanfan/wildfire-burn-window-decision-support.git}"
CODE_ROOT="${SLURM_TMPDIR:-/tmp}/flare-restart-code-${SLURM_JOB_ID:?}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/data/gpfs/projects/punim2936/portfolio_20260818/flare-artifacts/weather-restart-gate-${FLARE_GIT_COMMIT:0:7}}"
VENV="${SLURM_TMPDIR:-/tmp}/flare-restart-venv-${SLURM_JOB_ID:?}"
export PIP_CACHE_DIR="${SLURM_TMPDIR:-/tmp}/pip-cache-${SLURM_JOB_ID:?}"
trap 'rm -rf -- "${VENV}" "${PIP_CACHE_DIR}" "${CODE_ROOT}"' EXIT

for path in "${OUTPUT_ROOT}/baseline" "${OUTPUT_ROOT}/resumed" "${OUTPUT_ROOT}/gate"; do
  if [[ -e "${path}" ]]; then
    echo "refusing to overwrite existing restart-gate path: ${path}" >&2
    exit 2
  fi
done

git clone --filter=blob:none --no-checkout "${FLARE_REMOTE_URL}" "${CODE_ROOT}"
git -C "${CODE_ROOT}" checkout --detach "${FLARE_GIT_COMMIT}"
[[ "$(git -C "${CODE_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_COMMIT}" ]]
cd "${CODE_ROOT}"
module purge
module load GCCcore/11.3.0
module load Python/3.11.3
python -m venv "${VENV}"
"${VENV}/bin/python" -m pip install -e '.[public-data]'

COMMON=(--start 2024-03-01T00:00:00 --hours 336 --chunk-hours 168)
"${VENV}/bin/python" scripts/evaluate_public_weather_screen.py \
  --output "${OUTPUT_ROOT}/baseline" "${COMMON[@]}"

set +e
"${VENV}/bin/python" scripts/evaluate_public_weather_screen.py \
  --output "${OUTPUT_ROOT}/resumed" "${COMMON[@]}" --stop-after-chunks 1
controlled_exit=$?
set -e
if [[ "${controlled_exit}" != 75 ]]; then
  echo "controlled interruption returned ${controlled_exit}, expected 75" >&2
  exit 2
fi
"${VENV}/bin/python" scripts/evaluate_public_weather_screen.py \
  --output "${OUTPUT_ROOT}/resumed" "${COMMON[@]}" --resume

"${VENV}/bin/python" scripts/compare_public_weather_screen_restart.py \
  --baseline "${OUTPUT_ROOT}/baseline/metrics.json" \
  --resumed "${OUTPUT_ROOT}/resumed/metrics.json" \
  --output "${OUTPUT_ROOT}/gate"
