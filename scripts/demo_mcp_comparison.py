"""Three actual MCP comparison cases; detailed records stay in the source boundary."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from demo_mcp_climatology import redacted_diagnostics, stable_hash
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from burnwindows.burn_unit_climatology import RAIN_GUARD_WARNING, BurnUnitClimatologyCatalog
from burnwindows.manifest import git_sha, sha256_file


def independent_check(raw: dict[str, Any], derived: dict[str, Any]) -> int:
    """Client-side Decimal arithmetic; does not call comparison_view."""
    records = sorted(raw["records"], key=lambda row: (row["burn_id"], row["year"]))
    result_count = 0
    lookup = {(r["burn_id"], r["year"]): r for r in records}
    for summary in derived["period_summaries"]:
        selected = [r for r in records if r["burn_id"] == summary["burn_id"]]
        hours = sum(r["valid_hours"] for r in selected)
        numerator = sum(Decimal(str(r["weighted_suitable_area_fraction"]["mean"] or 0))
                        * Decimal(r["valid_hours"]) for r in selected)
        expected = float(numerator / Decimal(hours)) if hours else None
        actual = summary["valid_hour_weighted_mean_area_fraction"]
        assert (expected is None and actual is None) or math.isclose(expected, actual, abs_tol=1e-12)
        threshold = derived["annual_table"][0]["threshold"]
        suitable = sum(next(x["suitable_hours"] for x in r["threshold_sensitivity"]
                            if x["threshold"] == threshold) for r in selected)
        assert summary["suitable_hours"] == suitable and summary["valid_hours"] == hours
        assert summary["suitable_hour_fraction"] == (suitable / hours if hours else None)
        duration = derived["annual_table"][0]["duration_hours"]
        segments = sum(next(x["continuous_segments"][f"{duration}_hours"]
                            for x in r["threshold_sensitivity"] if x["threshold"] == threshold)
                       for r in selected)
        assert summary["annual_segment_sum_no_cross_year_stitch"] == segments
        result_count += 4
    for comparison in derived["comparisons"]:
        left = lookup[comparison["burn_id"], comparison["year"]]
        right = lookup[comparison["reference_burn_id"], comparison["reference_year"]]
        a, b = left["weighted_suitable_area_fraction"]["mean"], right["weighted_suitable_area_fraction"]["mean"]
        expected_delta = float((Decimal(str(a)) - Decimal(str(b))) * 100) if a is not None and b is not None else None
        actual_delta = comparison["mean_area_fraction_delta_percentage_points"]
        assert (expected_delta is None and actual_delta is None) or math.isclose(expected_delta, actual_delta, abs_tol=1e-12)
        result_count += 1
    assert len(derived["explanations"]) == len(records)
    assert "records" not in derived
    for source, table, explanation in zip(records, derived["annual_table"], derived["explanations"], strict=True):
        assert source["rule_sha256"] == table["rule_reference"]["prescription_workbook_sha256"]
        assert source["rule_sha256"] in explanation
        assert source["limiting_factor"]["constraint"] in explanation
        assert table["mean_area_fraction"] == source["weighted_suitable_area_fraction"]["mean"]
        result_count += 4
    return result_count


async def exercise(catalog: Path, artifact_id: str, burn_id: str, expected_sha: str) -> tuple[dict[str, Any], list[Any]]:
    # Catalog validation and selection are local to restricted execution.
    local = BurnUnitClimatologyCatalog(catalog)
    pool = local.query(artifact_id=artifact_id, year_start=2020, year_end=2020)
    ids = sorted({r["burn_id"] for r in pool.result["records"]})
    assert burn_id in ids
    peer = next(key for key in ids if key != burn_id)
    cases = [
        ("one_unit_two_years", [burn_id], 2020, 2021, {"reference_year": 2020}),
        ("two_units_same_year", [burn_id, peer], 2020, 2020, {"reference_burn_id": burn_id}),
        ("one_unit_five_years", [burn_id], 2019, 2023, {"reference_year": 2019}),
    ]
    root = Path(__file__).resolve().parents[1]
    server = StdioServerParameters(command=sys.executable,
        args=["-m", "burnwindows.mcp_server", "--artifact-catalog", str(catalog)],
        cwd=str(root), env={"PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1",
                           **({"LD_LIBRARY_PATH": os.environ["LD_LIBRARY_PATH"]}
                              if "LD_LIBRARY_PATH" in os.environ else {})})
    redacted, details = [], []
    async with (stdio_client(server) as (read, write),
                ClientSession(read, write, read_timeout_seconds=timedelta(seconds=60)) as session):
        await session.initialize()
        tools = await session.list_tools()
        assert [tool.name for tool in tools.tools] == ["get_burn_unit_climatology"]
        for name, burn_ids, start, end, reference in cases:
            request = {"artifact_id": artifact_id, "burn_ids": burn_ids,
                       "year_start": start, "year_end": end}
            raw_reply = await session.call_tool("get_burn_unit_climatology", request)
            comparison_reply = await session.call_tool("get_burn_unit_climatology", {
                **request, "view": "compare", "threshold": 0.8, "duration_hours": 4, **reference})
            assert not raw_reply.isError and not comparison_reply.isError
            raw, comparison = raw_reply.structuredContent, comparison_reply.structuredContent
            assert raw is not None and comparison is not None
            assert raw["result"]["artifact_sha256"] == expected_sha
            assert comparison["result"]["artifact_sha256"] == expected_sha
            assert comparison["provenance"]["status"] == "artifact_verified"
            assert comparison["warnings"] == raw["warnings"]
            assert RAIN_GUARD_WARNING in comparison["warnings"]
            checks = independent_check(raw["result"], comparison["result"])
            details.append({"case": name, "request": request, "comparison": comparison})
            redacted.append({"case": name, "row_count": raw["result"]["record_count"],
                "independent_arithmetic_and_provenance_checks": checks,
                "status": "passed", "result_sha256": stable_hash(comparison["result"]),
                "template_id": comparison["result"]["template_id"],
                "elapsed_ms": comparison["execution"]["elapsed_ms"],
                **redacted_diagnostics(comparison)})
    return {"code_sha": git_sha(), "scope": "deterministic_MCP_comparison_no_LLM",
            "catalog_sha256": sha256_file(catalog), "artifact_sha256": expected_sha,
            "tools_call_roundtrips": 6, "cases": redacted, "records_exported": False,
            "raw_weather_rescanned": False, "template_explanations_exported": False}, details


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-catalog", type=Path, required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--burn-id", required=True)
    parser.add_argument("--expected-catalog-sha256", required=True)
    parser.add_argument("--expected-artifact-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--restricted-detail-output", type=Path, required=True)
    parser.add_argument("--evidence-kind", choices=["real-precomputed", "synthetic-contract-fixture"], required=True)
    args = parser.parse_args()
    destinations = (args.output.resolve(), args.restricted_detail_output.resolve())
    if destinations[0] == destinations[1]:
        raise ValueError("redacted and restricted destinations must be distinct")
    if any(path == args.artifact_catalog.resolve() or path.exists() for path in destinations):
        raise ValueError("destinations must be new files, never existing inputs or reports")
    if sha256_file(args.artifact_catalog) != args.expected_catalog_sha256:
        raise ValueError("catalog SHA mismatch")
    # Prevent accidental raw table export from the approved source storage tree.
    if args.evidence_kind == "real-precomputed":
        allowed = Path("/data/gpfs/projects/punim1257/Group44/outputs").resolve()
        if not args.restricted_detail_output.resolve().is_relative_to(allowed):
            raise ValueError("real details must stay within approved Group44 output storage")
    report, details = asyncio.run(exercise(args.artifact_catalog, args.artifact_id,
                                         args.burn_id, args.expected_artifact_sha256))
    report["evidence_kind"] = args.evidence_kind
    for path, value in ((args.output, report), (args.restricted_detail_output, details)):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write((json.dumps(value, indent=2) + "\n").encode())
    print(json.dumps({"status": "passed", "cases": 3, "MCP_calls": 6,
                      "report_sha256": sha256_file(args.output)}))


if __name__ == "__main__":
    main()
