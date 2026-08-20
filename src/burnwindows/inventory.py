"""Metadata-only inventory for a large restricted NetCDF collection."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from .io import discover_climate_files


def _sample_indices(length: int, sample_count: int) -> list[int]:
    if sample_count <= 0:
        raise ValueError("sample_count must be positive")
    if length <= sample_count:
        return list(range(length))
    if sample_count == 1:
        return [0]
    return sorted({round(index * (length - 1) / (sample_count - 1)) for index in range(sample_count)})


def _collection_fingerprint(files: list[Path], root: Path) -> str:
    """Hash metadata, not restricted payload bytes, so large inventories stay cheap."""

    digest = hashlib.sha256()
    for path in files:
        stat = path.stat()
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = Path(path.name)
        digest.update(f"{relative.as_posix()}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def inventory_netcdf(input_path: str | Path, *, sample_count: int = 3) -> dict[str, Any]:
    """Inventory collection scale and validate representative NetCDF headers only."""

    import xarray as xr

    paths = [Path(value).resolve() for value in discover_climate_files(input_path)]
    root = Path(input_path).resolve() if Path(input_path).is_dir() else paths[0].parent
    samples: list[dict[str, Any]] = []
    for index in _sample_indices(len(paths), sample_count):
        path = paths[index]
        with xr.open_dataset(path, decode_times=True, chunks=None) as dataset:
            time_name = next(
                (name for name in ("time", "Time", "datetime") if name in dataset.coords),
                None,
            )
            time_range = None
            monotonic = None
            if time_name and dataset[time_name].size:
                values = dataset[time_name].values
                time_range = [str(values[0]), str(values[-1])]
                monotonic = bool((values[1:] > values[:-1]).all()) if len(values) > 1 else True
            samples.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "dimensions": {str(name): int(size) for name, size in dataset.sizes.items()},
                    "variables": sorted(str(name) for name in dataset.data_vars),
                    "variable_units": {
                        str(name): str(variable.attrs.get("units", ""))
                        for name, variable in dataset.data_vars.items()
                    },
                    "time_range": time_range,
                    "time_strictly_increasing": monotonic,
                }
            )
    total_bytes = sum(path.stat().st_size for path in paths)
    return {
        "inventory_kind": "metadata-only-no-payload-copy",
        "input_root": str(root),
        "file_count": len(paths),
        "total_bytes": total_bytes,
        "total_gib": total_bytes / (1024**3),
        "collection_metadata_sha256": _collection_fingerprint(paths, root),
        "sample_count": len(samples),
        "samples": samples,
        "host": os.uname().nodename if hasattr(os, "uname") else os.environ.get("COMPUTERNAME"),
    }
