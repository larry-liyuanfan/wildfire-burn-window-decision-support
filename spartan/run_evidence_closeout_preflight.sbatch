#!/bin/bash
#SBATCH --job-name=flare-evidence-closeout
#SBATCH --account=punim2936
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=00:20:00
#SBATCH --output=/data/gpfs/projects/punim2936/portfolio_20260903/flare-evidence-closeout/logs/%x-%j.out
#SBATCH --error=/data/gpfs/projects/punim2936/portfolio_20260903/flare-evidence-closeout/logs/%x-%j.err
set -euo pipefail

: "${EVIDENCE_ROOT:=/data/gpfs/projects/punim2936/portfolio_20260903/flare-evidence-closeout}"
: "${REPO_ROOT:=${EVIDENCE_ROOT}/repo}"

[[ "${EVIDENCE_ROOT}" == /data/gpfs/projects/punim2936/portfolio_20260903/flare-evidence-closeout ]] || {
  echo "EVIDENCE_ROOT must remain inside the authorised FLARE closeout directory" >&2
  exit 2
}
[[ -d "${REPO_ROOT}/.git" ]] || { echo "Missing Git checkout: ${REPO_ROOT}" >&2; exit 2; }

mkdir -p \
  "${EVIDENCE_ROOT}/.cache/pip" \
  "${EVIDENCE_ROOT}/.cache/xdg" \
  "${EVIDENCE_ROOT}/logs" \
  "${EVIDENCE_ROOT}/results"

export PIP_CACHE_DIR="${EVIDENCE_ROOT}/.cache/pip"
export XDG_CACHE_HOME="${EVIDENCE_ROOT}/.cache/xdg"
export PYTHONUNBUFFERED=1

module load Python/3.11.3
python -m venv "${EVIDENCE_ROOT}/.venv"
source "${EVIDENCE_ROOT}/.venv/bin/activate"
python -m pip install --upgrade pip
python -m pip install -e "${REPO_ROOT}[dev,serve]"

cd "${REPO_ROOT}"
test -z "$(git status --porcelain)"
python -m pytest
python -m ruff check .
python -m mypy \
  src/burnwindows/models.py \
  src/burnwindows/service.py \
  src/burnwindows/tool_benchmark.py
python -m burnwindows.tool_benchmark \
  --output "${EVIDENCE_ROOT}/results/fixture-preflight-${SLURM_JOB_ID}.json" \
  --repetitions 3 \
  --warmup 1 \
  --hours 168

git rev-parse HEAD > "${EVIDENCE_ROOT}/results/git-sha-${SLURM_JOB_ID}.txt"
python -m pip freeze > "${EVIDENCE_ROOT}/results/environment-${SLURM_JOB_ID}.txt"
python --version > "${EVIDENCE_ROOT}/results/python-${SLURM_JOB_ID}.txt"

