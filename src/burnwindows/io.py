"""Xarray/Dask I/O adapters for NetCDF, Zarr and Kerchunk references."""

from __future__ import annotations

import glob
import json
from pathlib import Path
from typing import Any

from .alignment import align_daily_dataarray
from .models import MissingPolicy, Prescription

VARIABLE_ALIASES = {
    "T_SFC": "temperature_c",
    "TSFC": "temperature_c",
    "RH_SFC": "relative_humidity_pct",
    "RHSFC": "relative_humidity_pct",
    "Wind_Mag_SFC": "wind_speed_kmh",
    "WMAG": "wind_speed_kmh",
    "FFDI": "FFDI",
    "KBDI-AWAP": "KBDI",
    "KBDI": "KBDI",
    "DF": "drought_factor",
}

VICCLIM6_FAMILIES: dict[str, tuple[str, str, str]] = {
    "T_SFC": ("WRFV6_TSFC1972-2024", "T_SFC", "hourly"),
    "RH_SFC": ("WRFV6_RHSFC1972-2024", "RH_SFC", "hourly"),
    "Wind_Mag_SFC": ("WRFV6_WMAG1972-2024", "Wind_Mag_SFC", "hourly"),
    "FFDI": ("WRFV6_FFDI1972-2024", "FFDI", "hourly"),
    "KBDI": ("WRFV6_KBDI1972-2024", "KBDI-AWAP", "daily"),
    "DF": ("WRFV6_DF1972-2024", "DF", "daily"),
}


def discover_climate_files(input_path: str | Path) -> list[str]:
    """Resolve a NetCDF file, directory or glob without opening payload data."""

    text = str(input_path)
    path = Path(text)
    if path.is_dir():
        result = sorted(str(item) for item in path.rglob("*.nc"))
    elif any(character in text for character in "*?["):
        result = sorted(glob.glob(text))
    elif path.is_file():
        result = [text]
    else:
        result = []
    if not result:
        raise FileNotFoundError(f"no input files found for {input_path}")
    return result


def open_climate_dataset(
    input_path: str | Path,
    *,
    backend: str = "netcdf",
    chunks: dict[str, int] | None = None,
) -> object:
    import xarray as xr

    chunks = chunks or {"time": 168}
    if backend == "netcdf":
        files = discover_climate_files(input_path)
        if len(files) == 1:
            return xr.open_dataset(files[0], chunks=chunks)
        return xr.open_mfdataset(files, combine="by_coords", chunks=chunks, parallel=True)
    if backend == "zarr":
        return xr.open_zarr(str(input_path), chunks=chunks, consolidated=None)
    if backend == "kerchunk":
        try:
            import fsspec
        except ImportError as exc:
            raise RuntimeError("install the 'kerchunk' optional dependencies") from exc
        mapper = fsspec.get_mapper(
            "reference://",
            fo=str(input_path),
            remote_protocol="file",
        )
        return xr.open_dataset(mapper, engine="zarr", chunks=chunks, consolidated=False)
    raise ValueError(f"unsupported backend: {backend}")


def _vicclim6_month_files(
    root: Path,
    family: str,
    start: object,
    end: object,
    *,
    include_previous_month: bool,
) -> list[str]:
    import pandas as pd

    start_period = pd.Timestamp(start).to_period("M")
    end_period = pd.Timestamp(end).to_period("M")
    if end_period < start_period:
        raise ValueError("end must not precede start")
    if include_previous_month:
        start_period -= 1
    paths: list[str] = []
    for period in pd.period_range(start_period, end_period, freq="M"):
        month_dir = root / family / f"{period.year:04d}" / f"{period.month:02d}"
        matches = sorted(month_dir.glob("*.nc"))
        if len(matches) != 1:
            raise FileNotFoundError(
                f"expected exactly one NetCDF in {month_dir}, found {len(matches)}"
            )
        paths.append(str(matches[0]))
    return paths


def open_vicclim6_period(
    input_path: str | Path,
    *,
    start: object,
    end: object,
    chunks: dict[str, int] | None = None,
    daily_availability_lag_hours: int = 24,
    daily_max_age_hours: int = 48,
) -> object:
    """Open one bounded VicClim6 period with leakage-safe daily/hourly alignment.

    Hourly temperature, relative humidity, wind and FFDI files define the
    target grid. Date-labelled daily KBDI and drought factor are shifted by the
    declared availability lag and only backward-filled within a bounded age.
    A previous-month file is loaded only when the requested start precedes the
    first current-month observation becoming available.
    """

    import pandas as pd
    import xarray as xr

    root = Path(input_path)
    if not root.is_dir():
        raise FileNotFoundError(root)
    start_time = pd.Timestamp(start)
    end_time = pd.Timestamp(end)
    if end_time < start_time:
        raise ValueError("end must not precede start")
    target_time = pd.date_range(start_time, end_time, freq="h")
    if not len(target_time):
        raise ValueError("requested VicClim6 period is empty")
    chunks = chunks or {"time": 168}

    month_start = start_time.to_period("M").start_time
    needs_previous_daily_month = start_time < (
        month_start + pd.Timedelta(hours=daily_availability_lag_hours)
    )
    variables: dict[str, object] = {}
    for output_name, (family, source_name, cadence) in VICCLIM6_FAMILIES.items():
        paths = _vicclim6_month_files(
            root,
            family,
            start_time,
            end_time,
            include_previous_month=cadence == "daily" and needs_previous_daily_month,
        )
        dataset = xr.open_mfdataset(
            paths,
            combine="by_coords",
            parallel=True,
            chunks=chunks,
        )
        if source_name not in dataset:
            raise KeyError(f"{source_name} is missing from {paths[0]}")
        values = dataset[source_name]
        if cadence == "daily":
            values = align_daily_dataarray(
                values,
                target_time,
                availability_lag_hours=daily_availability_lag_hours,
                max_age_hours=daily_max_age_hours,
            )
        else:
            values = values.reindex(time=target_time)
        variables[output_name] = values
    return xr.Dataset(variables).assign_attrs(
        {
            "source": "VicClim6 Group44 GPFS",
            "daily_alignment": "backward-only",
            "daily_availability_lag_hours": daily_availability_lag_hours,
            "daily_max_age_hours": daily_max_age_hours,
        }
    )


def normalise_dataset(dataset: object) -> tuple[object, list[str]]:
    """Rename recognised variables and convert only units declared in attrs."""

    rename: dict[str, str] = {}
    claimed = set(dataset.variables)
    for source, target in VARIABLE_ALIASES.items():
        if source in dataset and target not in claimed:
            rename[source] = target
            claimed.add(target)
    result = dataset.rename(rename)
    warnings: list[str] = []
    if "temperature_c" in result:
        units = str(result.temperature_c.attrs.get("units", "")).lower()
        if units in {"k", "kelvin"}:
            result["temperature_c"] = result.temperature_c - 273.15
            result.temperature_c.attrs["units"] = "degC"
        elif units not in {"c", "degc", "degree_celsius", "degrees celsius", "°c"}:
            warnings.append("temperature units are absent or unrecognised; values were not converted")
    if "relative_humidity_pct" in result:
        units = str(result.relative_humidity_pct.attrs.get("units", "")).lower()
        if units in {"1", "fraction", "ratio"}:
            result["relative_humidity_pct"] = result.relative_humidity_pct * 100.0
            result.relative_humidity_pct.attrs["units"] = "%"
        elif units not in {"%", "percent", "percentage"}:
            warnings.append("relative-humidity units are absent or unrecognised; values were not converted")
    if "wind_speed_kmh" in result:
        units = str(result.wind_speed_kmh.attrs.get("units", "")).lower().replace(" ", "")
        if units in {"m/s", "ms-1", "m.s-1"}:
            result["wind_speed_kmh"] = result.wind_speed_kmh * 3.6
            result.wind_speed_kmh.attrs["units"] = "km/h"
        elif units in {"kt", "kts", "knot", "knots"}:
            result["wind_speed_kmh"] = result.wind_speed_kmh * 1.852
            result.wind_speed_kmh.attrs["units"] = "km/h"
        elif units not in {"km/h", "kmh-1", "kmhr-1"}:
            warnings.append("wind-speed units are absent or unrecognised; values were not converted")
    return result, warnings


def ensure_hourly_grid(dataset: object) -> object:
    """Insert missing hourly timestamps so gaps cannot bridge a window."""

    import pandas as pd

    if "time" not in dataset.coords:
        raise ValueError("dataset needs a time coordinate")
    index = pd.DatetimeIndex(dataset.time.values)
    if not index.is_monotonic_increasing or index.has_duplicates:
        raise ValueError("time coordinate must be strictly increasing")
    if not len(index):
        return dataset
    complete = pd.date_range(index[0], index[-1], freq="h")
    return dataset.reindex(time=complete) if len(complete) != len(index) else dataset


def evaluate_xarray(
    dataset: object,
    prescription: Prescription,
    *,
    missing_policy: MissingPolicy = MissingPolicy.ERROR,
    include_unmapped: bool = False,
) -> tuple[object, dict[str, object], list[str]]:
    import xarray as xr

    if "time" not in dataset.coords:
        raise ValueError("dataset needs a time coordinate")
    template = next(iter(dataset.data_vars.values()))
    combined = xr.ones_like(template, dtype=bool)
    masks: dict[str, object] = {}
    warnings: list[str] = []
    for index, condition in enumerate(prescription.conditions):
        key = f"{condition.field}:{index}"
        if condition.operational_status == "unmapped" and not include_unmapped:
            warnings.append(f"excluded unmapped constraint: {condition.field}")
            continue
        if condition.variable not in dataset:
            message = f"missing variable {condition.variable} for {condition.field}"
            if missing_policy == MissingPolicy.ERROR:
                raise KeyError(message)
            warnings.append(message)
            mask = xr.zeros_like(template, dtype=bool) if missing_policy == MissingPolicy.FAIL else xr.ones_like(template, dtype=bool)
        else:
            values = dataset[condition.variable]
            mask = values.notnull()
            if condition.lower:
                mask &= values >= condition.lower.value if condition.lower.inclusive else values > condition.lower.value
            if condition.upper:
                mask &= values <= condition.upper.value if condition.upper.inclusive else values < condition.upper.value
        if condition.season:
            months = set({"summer": [12, 1, 2], "autumn": [3, 4, 5], "winter": [6, 7, 8], "spring": [9, 10, 11]}[condition.season])
            active = dataset.time.dt.month.isin(months)
            mask = xr.where(active, mask, True)
        masks[key] = mask
        combined &= mask
    combined.name = "suitable"
    return combined, masks, warnings


def inspect_dataset(dataset: object) -> dict[str, Any]:
    return {
        "dimensions": {str(name): int(size) for name, size in dataset.sizes.items()},
        "variables": sorted(str(name) for name in dataset.data_vars),
        "chunks": {
            str(name): [list(map(int, chunk)) for chunk in variable.chunks] if variable.chunks else None
            for name, variable in dataset.data_vars.items()
        },
        "time_range": [str(dataset.time.values[0]), str(dataset.time.values[-1])]
        if "time" in dataset and dataset.time.size
        else None,
    }


def parse_chunks(text: str | None) -> dict[str, int]:
    if not text:
        return {"time": 168}
    value = json.loads(text)
    if not isinstance(value, dict) or not all(isinstance(item, int) and item > 0 for item in value.values()):
        raise ValueError("chunks must be a JSON object of positive integers")
    return value
