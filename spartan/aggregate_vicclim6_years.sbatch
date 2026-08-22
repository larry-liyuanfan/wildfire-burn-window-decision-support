#!/bin/bash
#SBATCH --job-name=vicclim6-aggregate
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:05:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

set -euo pipefail
module purge
module load "${FLARE_TOOLCHAIN_MODULE:-GCCcore/11.3.0}"
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"
export PYTHONUNBUFFERED=1

: "${PROJECT_ROOT:?Set the exact FLARE repository checkout}"
: "${FLARE_GIT_SHA:?Pin the pushed commit to execute}"
: "${FLARE_PYTHON:?Set the FLARE environment Python executable}"
: "${YEAR_RUN_ROOT:?Set the annual result root}"
: "${SUMMARY_OUTPUT:?Set a compact JSON output path}"

[[ "$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_SHA}" ]] || {
  echo "checkout does not match FLARE_GIT_SHA" >&2
  exit 2
}
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"
srun "${FLARE_PYTHON}" -c \
  'from burnwindows.cli import main; raise SystemExit(main())' \
  aggregate-vicclim6 \
  --input "${YEAR_RUN_ROOT}" \
  --year-start 1973 \
  --year-end 2023 \
  --output "${SUMMARY_OUTPUT}"
