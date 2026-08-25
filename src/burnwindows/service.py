"""Fail-closed FastAPI service for the deterministic FLARE tool registry."""

from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, Field

from .models import (
    DeriveFuelInputsRequest,
    ExplainLimitingFactorsRequest,
    FindBurnWindowsRequest,
    OptimizeScheduleRequest,
    RegionTrendRequest,
    ThresholdScenarioRequest,
    ToolEnvelope,
)
from .tools import (
    compare_threshold_scenarios,
    derive_fuel_inputs,
    explain_limiting_factors,
    find_burn_windows,
    get_region_trend,
    optimize_burn_schedule,
    tool_schemas,
)

TOOL_REGISTRY: dict[str, tuple[type[BaseModel], Callable[..., ToolEnvelope]]] = {
    "find_burn_windows": (FindBurnWindowsRequest, find_burn_windows),
    "explain_limiting_factors": (ExplainLimitingFactorsRequest, explain_limiting_factors),
    "compare_threshold_scenarios": (ThresholdScenarioRequest, compare_threshold_scenarios),
    "get_region_trend": (RegionTrendRequest, get_region_trend),
    "optimize_burn_schedule": (OptimizeScheduleRequest, optimize_burn_schedule),
    "derive_fuel_inputs": (DeriveFuelInputsRequest, derive_fuel_inputs),
}


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any]


class BurnUnitClimatologyJobRequest(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=200)
    burn_ids: list[str] = Field(default_factory=list, max_length=500)
    metrics: list[str] = Field(default_factory=list, max_length=20)


class _JobStore:
    def __init__(self, runner: Callable[[dict[str, Any]], Any] | None) -> None:
        self.runner = runner
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flare-tool-job")
        self.lock = threading.Lock()
        self.rows: dict[str, dict[str, Any]] = {}

    def submit(self, payload: dict[str, Any]) -> str:
        job_id = uuid.uuid4().hex
        with self.lock:
            self.rows[job_id] = {"job_id": job_id, "status": "queued", "request": payload}

        def run() -> None:
            with self.lock:
                self.rows[job_id]["status"] = "running"
            try:
                if self.runner is None:
                    raise RuntimeError("burn-unit climatology runner is not configured")
                result = self.runner(payload)
                with self.lock:
                    self.rows[job_id].update({"status": "completed", "result": result})
            except Exception as exc:  # noqa: BLE001 - job state must be fail-closed
                with self.lock:
                    self.rows[job_id].update(
                        {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
                    )

        self.executor.submit(run)
        return job_id

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.rows.get(job_id)
            return dict(row) if row else None


def create_app(
    *,
    climatology_runner: Callable[[dict[str, Any]], Any] | None = None,
    tool_registry: Mapping[str, tuple[type[BaseModel], Callable[..., ToolEnvelope]]] | None = None,
):
    try:
        from fastapi import FastAPI, HTTPException, Response
    except ImportError as exc:
        raise RuntimeError("FastAPI is unavailable; install the 'serve' extra") from exc

    registry = dict(tool_registry or TOOL_REGISTRY)
    jobs = _JobStore(climatology_runner)
    counters: dict[str, int] = defaultdict(int)
    latencies: list[float] = []
    metric_lock = threading.Lock()
    app = FastAPI(
        title="FLARE Trusted Burn-window Tool Service",
        version="0.2.0",
        description=(
            "Typed deterministic tools. The service rejects undeclared fields and never lets "
            "a language model modify prescriptions or execute arbitrary expressions."
        ),
    )

    @app.get("/api/tools")
    def list_tools() -> dict[str, Any]:
        schemas = tool_schemas()
        return {"tools": {name: schemas[name] for name in sorted(registry)}}

    @app.post("/api/tools/{tool_name}:invoke")
    def invoke_tool(tool_name: str, request: ToolInvokeRequest) -> dict[str, Any]:
        if tool_name not in registry:
            raise HTTPException(status_code=404, detail="unknown tool")
        request_model, function = registry[tool_name]
        unexpected = sorted(set(request.arguments) - set(request_model.model_fields))
        if unexpected:
            raise HTTPException(
                status_code=422,
                detail={"reason": "undeclared_fields", "fields": unexpected},
            )
        trace_id = uuid.uuid4().hex
        started = time.perf_counter()
        try:
            parsed = request_model.model_validate(request.arguments)
            envelope = function(**parsed.model_dump())
            envelope = envelope.model_copy(update={"trace_id": trace_id})
            status = "ok"
        except (TypeError, ValueError) as exc:
            with metric_lock:
                counters[f"{tool_name}:rejected"] += 1
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        latency_ms = (time.perf_counter() - started) * 1000.0
        with metric_lock:
            counters[f"{tool_name}:{status}"] += 1
            latencies.append(latency_ms)
        return envelope.model_dump(mode="json")

    @app.post("/api/jobs/burn-unit-climatology", status_code=202)
    def submit_climatology(request: BurnUnitClimatologyJobRequest) -> dict[str, str]:
        job_id = jobs.submit(request.model_dump())
        return {"job_id": job_id, "status": "queued"}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        row = jobs.get(job_id)
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        return row

    @app.get("/metrics")
    def metrics() -> Response:
        with metric_lock:
            lines = ["# TYPE flare_tool_requests_total counter"]
            for key, value in sorted(counters.items()):
                tool, status = key.split(":", 1)
                lines.append(
                    f'flare_tool_requests_total{{tool="{tool}",status="{status}"}} {value}'
                )
            if latencies:
                ordered = sorted(latencies)
                lines.append("# TYPE flare_tool_latency_ms gauge")
                for label, quantile in (("p50", 0.50), ("p95", 0.95)):
                    index = min(len(ordered) - 1, int(quantile * len(ordered)))
                    lines.append(
                        f'flare_tool_latency_ms{{quantile="{label}"}} {ordered[index]:.6f}'
                    )
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    return app

