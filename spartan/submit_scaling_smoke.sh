#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(git rev-parse --show-toplevel)"
PORTFOLIO_ROOT="$(dirname "${PROJECT_ROOT}")"
ARTIFACT_ROOT="${PORTFOLIO_ROOT}/flare-artifacts"
HOURS="${1:-2160}"
CELLS="${2:-1024}"

mkdir -p "${ARTIFACT_ROOT}"
sbatch --partition=sapphire \
  --export=ALL,PROJECT_ROOT="${PROJECT_ROOT}",IMAGE_PATH="${ARTIFACT_ROOT}/flare-tools.sif",OUTPUT_ROOT="${ARTIFACT_ROOT}",BENCHMARK_HOURS="${HOURS}",BENCHMARK_CELLS="${CELLS}" \
  spartan/run_scaling_benchmark.sbatch
