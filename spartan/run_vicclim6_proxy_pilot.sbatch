#!/bin/bash
#SBATCH --job-name=vicclim6-proxy-pilot
#SBATCH --account=punim1257
#SBATCH --partition=sapphire
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:10:00
#SBATCH --output=logs/%x-%j.out
#SBATCH --error=logs/%x-%j.err

set -euo pipefail
module purge
module load "${FLARE_TOOLCHAIN_MODULE:-GCCcore/11.3.0}"
module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"
export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export PYTHONUNBUFFERED=1

: "${PROJECT_ROOT:?Set the exact FLARE repository checkout}"
: "${FLARE_GIT_SHA:?Pin the pushed commit to execute}"
: "${FLARE_PYTHON:?Set the FLARE environment Python executable}"
: "${VICCLIM_ROOT:?Set the Group44 VicClim6 root}"
: "${PRESCRIPTIONS:?Set the restricted FMS workbook path}"
: "${REGION_GEOJSON:?Set the approved Murray Goldfields boundary}"
: "${OUTPUT_ROOT:?Use approved Group44 project output storage}"

BURN_CLASS="${BURN_CLASS:-Murray Goldfields - Box ironbark forest}"
START_TIME="${START_TIME:-2020-01-01T00:00:00}"
END_TIME="${END_TIME:-2020-12-31T23:00:00}"
WIND_REDUCTION_FACTOR="${WIND_REDUCTION_FACTOR:-0.33}"
FMC_RAIN_GUARD_MM="${FMC_RAIN_GUARD_MM:-0.2}"
RUN_DIR="${OUTPUT_ROOT}/vicclim6-proxy-pilot-${SLURM_JOB_ID}"

[[ -x "${FLARE_PYTHON}" ]] || { echo "FLARE Python is not executable" >&2; exit 2; }
[[ -r "${PRESCRIPTIONS}" ]] || { echo "FMS workbook is not readable" >&2; exit 2; }
[[ -r "${REGION_GEOJSON}" ]] || { echo "region GeoJSON is not readable" >&2; exit 2; }
[[ -r "${VICCLIM_ROOT}/WRFV6_TSFC1972-2024/2020/01/IDV71000_VIC_T_SFC.nc" ]] || {
  echo "canonical VicClim6 sample is not readable" >&2
  exit 2
}
[[ "$(git -C "${PROJECT_ROOT}" rev-parse HEAD)" == "${FLARE_GIT_SHA}" ]] || {
  echo "checkout does not match FLARE_GIT_SHA" >&2
  exit 2
}

mkdir -p "${PROJECT_ROOT}/logs" "${OUTPUT_ROOT}"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src:${PYTHONPATH:-}"

srun "${FLARE_PYTHON}" -c \
  'from burnwindows.cli import main; raise SystemExit(main())' \
  analyse \
  --backend vicclim6 \
  --input "${VICCLIM_ROOT}" \
  --prescriptions "${PRESCRIPTIONS}" \
  --burn-class "${BURN_CLASS}" \
  --start "${START_TIME}" \
  --end "${END_TIME}" \
  --chunks '{"time":168,"latitude":37,"longitude":61}' \
  --scheduler synchronous \
  --dask-workers 1 \
  --durations 2 4 6 \
  --missing-policy error \
  --data-kind real \
  --region-geojson "${REGION_GEOJSON}" \
  --region-label "Murray Goldfields FFMVic district" \
  --derive-fuel-proxies \
  --wind-reduction-factor "${WIND_REDUCTION_FACTOR}" \
  --fmc-rain-guard-mm "${FMC_RAIN_GUARD_MM}" \
  --output-dir "${RUN_DIR}"
