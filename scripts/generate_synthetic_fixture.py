"""Create a deterministic NetCDF fixture. This is never real-project evidence."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hours", type=int, default=72)
    args = parser.parse_args()
    rng = np.random.default_rng(20260818)
    time = pd.date_range("2024-03-01", periods=args.hours, freq="h")
    lat = [-37.8, -37.7]
    lon = [147.0, 147.1]
    shape = (len(time), len(lat), len(lon))
    dataset = xr.Dataset(
        {
            "T_SFC": (("time", "lat", "lon"), rng.normal(20, 4, shape), {"units": "degC"}),
            "RHSFC": (("time", "lat", "lon"), rng.normal(50, 12, shape), {"units": "%"}),
            "WMAG": (("time", "lat", "lon"), rng.normal(4, 1, shape), {"units": "m/s"}),
            "FFDI": (("time", "lat", "lon"), rng.uniform(0, 20, shape)),
            "KBDI": (("time", "lat", "lon"), rng.uniform(0, 100, shape)),
        },
        coords={"time": time, "lat": lat, "lon": lon},
        attrs={"data_kind": "deterministic-synthetic-test-fixture", "seed": 20260818},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(args.output, engine="h5netcdf")
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

