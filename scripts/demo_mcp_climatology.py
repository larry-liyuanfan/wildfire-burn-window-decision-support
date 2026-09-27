"""Real MCP stdio client. Emit only redacted checks, never compact records."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from burnwindows.manifest import git_sha, sha256_file


def stable_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def redacted_diagnostics(value: dict[str, Any]) -> dict[str, Any]:
    warnings = value["warnings"]
    codes = set()
    for warning in warnings:
        if warning == "precipitation field absent; FMC rain guard was not applied":
            codes.add("precipitation_unavailable")
        elif warning.startswith("unknown burn IDs omitted:"):
            codes.add("unknown_burn_ids")
        elif warning == "no verified compact result was published for this invocation":
            codes.add("no_verified_result")
        else:
            codes.add("other_warning_present")
    return {
        "warning_codes": sorted(codes),
        "warning_count": len(warnings),
        "warnings_sha256": stable_hash(warnings),
        "constraint_count": len(value["constraints"]),
        "constraints_sha256": stable_hash(value["constraints"]),
    }


async def exercise(
    catalog: Path, artifact_id: str, burn_id: str, expected_artifact_sha256: str | None = None
) -> dict[str, Any]:
    request = {
        "artifact_id": artifact_id,
        "burn_ids": [burn_id],
        "year_start": 2020,
        "year_end": 2020,
    }
    source = str(Path(__file__).resolve().parents[1] / "src")
    cases = []
    result_sha = None
    tool_names = []
    for configured in (True, False):
        arguments = ["-m", "burnwindows.mcp_server"]
        if configured:
            arguments += ["--artifact-catalog", str(catalog)]
        server = StdioServerParameters(
            command=sys.executable,
            args=arguments,
            env={
                "PYTHONPATH": source,
                "PYTHONDONTWRITEBYTECODE": "1",
                **(
                    {"LD_LIBRARY_PATH": os.environ["LD_LIBRARY_PATH"]}
                    if "LD_LIBRARY_PATH" in os.environ
                    else {}
                ),
            },
            cwd=str(Path(__file__).resolve().parents[1]),
        )
        async with (
            stdio_client(server) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=60)) as session,
        ):
            await session.initialize()
            listed = await session.list_tools()
            tool_names = [tool.name for tool in listed.tools]
            assert tool_names == ["get_burn_unit_climatology"]
            assert listed.tools[0].inputSchema["additionalProperties"] is False
            assert listed.tools[0].outputSchema is not None
            assert listed.tools[0].annotations.readOnlyHint is True
            requests = (
                [
                    ("valid", request),
                    ("repeat", request),
                    ("unknown_burn", {**request, "burn_ids": ["unknown-burn-contract-case"]}),
                    ("illegal_argument", {**request, "artifact_path": "not-allowed.json"}),
                    ("unknown_artifact", {**request, "artifact_id": "not-allowlisted"}),
                ]
                if configured
                else [("catalog_unavailable", request)]
            )
            for case_id, payload in requests:
                reply = await session.call_tool("get_burn_unit_climatology", payload)
                value = reply.structuredContent
                assert value is not None
                result = value["result"]
                if case_id in {"valid", "repeat"}:
                    assert not reply.isError and value["status"] == "ok"
                    assert value["provenance"]["status"] == "artifact_verified"
                    assert result["record_count"] == 1
                    if expected_artifact_sha256 is not None:
                        assert result["artifact_sha256"] == expected_artifact_sha256
                    record = result["records"][0]
                    assert record["burn_id"] == burn_id and record["year"] == 2020
                    assert record["rule_sha256"] and record["data_sha256"]
                    assert value["constraints"] and value["warnings"]
                    if result_sha is None:
                        result_sha = stable_hash(result)
                    else:
                        assert result_sha == stable_hash(result)
                elif case_id == "unknown_burn":
                    assert not reply.isError and value["status"] == "partial"
                    assert result["record_count"] == 0 and value["warnings"]
                else:
                    assert reply.isError and value["status"] == "error"
                    assert result is None and value["provenance"]["status"] == "incomplete"
                cases.append(
                    {
                        "case": case_id,
                        "protocol_is_error": reply.isError,
                        "status": value["status"],
                        "record_count": result["record_count"] if result else 0,
                        "provenance_status": value["provenance"]["status"],
                        "error_code": value["error"]["code"] if value["error"] else None,
                        "data_version": value["data_version"],
                        "request_sha256": value["provenance"]["request_sha256"],
                        "result_sha256": stable_hash(result),
                        **redacted_diagnostics(value),
                        "record_provenance_present": bool(
                            result
                            and result["records"]
                            and all(
                                key in result["records"][0]
                                for key in (
                                    "data_sha256",
                                    "rule_sha256",
                                    "spatial_sha256",
                                    "git_sha",
                                )
                            )
                        ),
                    }
                )
    return {
        "scope": "read_only_MCP_stdio_application_check_not_LLM_or_weather_evaluation",
        "git_sha": git_sha(),
        "sdk": "official modelcontextprotocol/python-sdk",
        "mcp_version": version("mcp"),
        "python": sys.version.split()[0],
        "catalog_sha256": sha256_file(catalog),
        "tool_names": tool_names,
        "tools_list_roundtrips": 2,
        "tools_call_roundtrips": len(cases),
        "repeated_result_identical": True,
        "records_exported": False,
        "cases": cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-catalog", required=True, type=Path)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--burn-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--expected-catalog-sha256")
    parser.add_argument("--expected-artifact-sha256")
    parser.add_argument(
        "--evidence-kind", choices=["real-precomputed", "synthetic-contract-fixture"], required=True
    )
    args = parser.parse_args()
    if args.evidence_kind == "real-precomputed" and not (
        args.expected_catalog_sha256 and args.expected_artifact_sha256
    ):
        raise ValueError(
            "real-precomputed requires independently recorded catalog and artifact SHAs"
        )
    if (
        args.expected_catalog_sha256
        and sha256_file(args.artifact_catalog) != args.expected_catalog_sha256
    ):
        raise ValueError("catalog SHA mismatch")
    result = asyncio.run(
        exercise(
            args.artifact_catalog, args.artifact_id, args.burn_id, args.expected_artifact_sha256
        )
    )
    result["evidence_kind"] = args.evidence_kind
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "passed",
                "tools_call_roundtrips": 6,
                "evidence_kind": args.evidence_kind,
                "report_sha256": sha256_file(args.output),
            }
        )
    )


if __name__ == "__main__":
    main()
