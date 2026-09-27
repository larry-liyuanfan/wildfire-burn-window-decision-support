"""Read-only MCP stdio boundary over precomputed burn-ID results; no LLM or writes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path
from typing import Annotated, Any

from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import ConfigDict, Field, StringConstraints, ValidationError, model_validator

from .burn_unit_climatology import BurnUnitClimatologyCatalog, get_burn_unit_climatology
from .manifest import git_sha
from .models import BurnUnitClimatologyRequest, ToolEnvelope
from .service import _error_envelope, _service_envelope

TOOL_NAME = "get_burn_unit_climatology"
BurnID = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class MCPClimatologyRequest(BurnUnitClimatologyRequest):
    """Bounded read, up to 25 records; callers cannot supply paths or expressions."""

    model_config = ConfigDict(extra="forbid", strict=True)
    burn_ids: list[BurnID] = Field(min_length=1, max_length=5)
    year_start: int = Field(ge=1973, le=2023)
    year_end: int = Field(ge=1973, le=2023)

    @model_validator(mode="after")
    def bounded_years(self) -> MCPClimatologyRequest:
        if self.year_end - self.year_start > 4:
            raise ValueError("MCP query is limited to five years")
        return self


def create_server(catalog_path: Path | None, *, timeout_seconds: float = 10.0) -> Server:
    if not 0.001 <= timeout_seconds <= 30:
        raise ValueError("timeout must be in [0.001, 30] seconds")
    catalog = None
    if catalog_path is not None:
        try:
            catalog = BurnUnitClimatologyCatalog(catalog_path)
        except (OSError, ValueError, TypeError, KeyError):
            # Keep a discoverable failure path, without leaking operator paths.
            catalog = None
    code_sha = git_sha()
    server = Server("flare-readonly-climatology", version="0.1.0")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=TOOL_NAME,
                description=(
                    "Read a hash-verified precomputed burn-ID climatology artifact. "
                    "Up to 5 IDs x 5 years. Preserves proxy/missing-data warnings. "
                    "Not operational approval, safety evidence, outcome or ROI."
                ),
                inputSchema=MCPClimatologyRequest.model_json_schema(),
                outputSchema=ToolEnvelope.model_json_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=True,
                    destructiveHint=False,
                    idempotentHint=True,
                    openWorldHint=False,
                ),
            )
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        started = time.perf_counter()
        request_sha = hashlib.sha256(
            json.dumps({"tool": name, "arguments": arguments}, sort_keys=True).encode()
        ).hexdigest()
        error_code = "tool_error"
        error_message = "No result was published."
        try:
            if name != TOOL_NAME:
                raise ValueError("unknown tool")
            request = MCPClimatologyRequest.model_validate(arguments)
            if catalog is None:
                error_code = "catalog_unavailable"
                raise RuntimeError("catalog unavailable")
            envelope = await asyncio.wait_for(
                asyncio.to_thread(get_burn_unit_climatology, catalog, **request.model_dump()),
                timeout=timeout_seconds,
            )
        except ValidationError:
            error_code = "invalid_arguments"
            error_message = "Arguments violate the published tool schema or bounded query contract."
        except (TimeoutError, asyncio.TimeoutError):
            error_code = "timeout"
            error_message = "Read-only query deadline exceeded; no result published."
        except (ValueError, RuntimeError):
            error_message = "Tool/artifact is not available in the operator-controlled catalog."
        else:
            envelope = _service_envelope(
                envelope,
                tool_name=TOOL_NAME,
                request_sha256=request_sha,
                timeout_seconds=timeout_seconds,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                idempotency_key=None,
                code_sha=code_sha,
            )
            payload = envelope.model_dump(mode="json")
            return types.CallToolResult(
                isError=False,
                structuredContent=payload,
                content=[types.TextContent(type="text", text=json.dumps(payload))],
            )
        envelope = _error_envelope(
            tool_name=TOOL_NAME,
            data_version="unknown",
            request_sha256=request_sha,
            timeout_seconds=timeout_seconds,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            idempotency_key=None,
            code=error_code,
            message=error_message,
            retryable=error_code == "timeout",
            code_sha=code_sha,
        )
        payload = envelope.model_dump(mode="json")
        return types.CallToolResult(
            isError=True,
            structuredContent=payload,
            content=[types.TextContent(type="text", text=json.dumps(payload))],
        )

    return server


async def run(catalog_path: Path | None, timeout_seconds: float) -> None:
    server = create_server(catalog_path, timeout_seconds=timeout_seconds)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-catalog", type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()
    asyncio.run(run(args.artifact_catalog, args.timeout_seconds))


if __name__ == "__main__":
    main()
