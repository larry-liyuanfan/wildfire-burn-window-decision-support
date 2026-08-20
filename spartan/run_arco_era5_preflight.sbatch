#!/bin/bash
#SBATCH --job-name=flare-arco-preflight
#SBATCH --partition=cascade
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=16G
#SBATCH --time=00:20:00
#SBATCH --output=/data/gpfs/projects/punim2936/portfolio_20260818/flare-artifacts/logs/%x-%j.out
set -euo pipefail

SOURCE_REPO="${REPO_DIR:-/data/gpfs/projects/punim2936/portfolio_20260818/flare-tools}"
FLARE_GIT_COMMIT="${FLARE_GIT_COMMIT:-$(git -C "${SOURCE_REPO}" rev-parse HEAD)}"
git -C "${SOURCE_REPO}" cat-file -e "${FLARE_GIT_COMMIT}^{commit}"
CODE_ROOT="${SLURM_TMPDIR:-/tmp}/flare-code-${SLURM_JOB_ID:?}"
git clone --shared --no-checkout "${SOURCE_REPO}" "${CODE_ROOT}"
git -C "${CODE_ROOT}" checkout --detach "${FLARE_GIT_COMMIT}"
cd "${CODE_ROOT}"
OUTPUT_DIR="${OUTPUT_DIR:-/data/gpfs/projects/punim2936/portfolio_20260818/flare-artifacts/arco-era5-preflight-${FLARE_GIT_COMMIT:0:7}}"
VENV="${SLURM_TMPDIR:-/tmp}/flare-arco-venv-${SLURM_JOB_ID:?}"
export PIP_CACHE_DIR="${SLURM_TMPDIR:-/tmp}/pip-cache-${SLURM_JOB_ID:?}"
trap 'rm -rf -- "${VENV}" "${PIP_CACHE_DIR}" "${CODE_ROOT}"' EXIT
module purge
module load GCCcore/11.3.0
module load Python/3.11.3
python -m venv "${VENV}"
"${VENV}/bin/python" -m pip install -e '.[public-data]'
/usr/bin/time -v "${VENV}/bin/python" scripts/preflight_arco_era5.py \
  --output "${OUTPUT_DIR}" \
  --start 2024-02-01T00:00:00 \
  --hours 24
