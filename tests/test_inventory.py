from __future__ import annotations

from pathlib import Path

import numpy as np
import xarray as xr

from burnwindows.inventory import inventory_netcdf


def test_inventory_records_collection_scale_and_representative_headers(tmp_path) -> None:
    for month in range(1, 4):
        dataset = xr.Dataset(
            {"T_SFC": ("time", [290.0, 291.0], {"units": "K"})},
            coords={
                "time": np.array(
                    [f"2026-{month:02d}-01T00", f"2026-{month:02d}-01T01"],
                    dtype="datetime64[h]",
                )
            },
        )
        dataset.to_netcdf(tmp_path / f"temperature-{month:02d}.nc")

    result = inventory_netcdf(tmp_path, sample_count=3)

    assert result["inventory_kind"] == "metadata-only-no-payload-copy"
    assert result["file_count"] == 3
    assert result["total_bytes"] > 0
    assert len(result["collection_metadata_sha256"]) == 64
    assert [sample["relative_path"] for sample in result["samples"]] == [
        "temperature-01.nc",
        "temperature-02.nc",
        "temperature-03.nc",
    ]
    assert all(sample["time_strictly_increasing"] for sample in result["samples"])
    assert result["samples"][0]["variable_units"]["T_SFC"] == "K"


def test_spartan_venv_preflight_loads_the_python_module_used_to_build_the_venv() -> None:
    script = (
        Path(__file__).parents[1] / "spartan" / "run_real_preflight_venv.sbatch"
    ).read_text(encoding="utf-8")

    assert 'module load "${FLARE_PYTHON_MODULE:-Python/3.11.3}"' in script
    assert script.index("module load") < script.index('[[ -x "${FLARE_PYTHON}" ]]')
