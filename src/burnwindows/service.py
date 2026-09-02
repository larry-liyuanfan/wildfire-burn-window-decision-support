"""Fail-closed FastAPI service for the deterministic FLARE tool registry."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import OrderedDict, defaultdict
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .manifest import git_sha
from .models import (
    DeriveFuelInputsRequest,
    ExplainLimitingFactorsRequest,
    FindBurnWindowsRequest,
    OptimizeScheduleRequest,
    RegionTrendRequest,
    ThresholdScenarioRequest,
    ToolEnvelope,
    ToolError,
    ToolExecution,
    ToolProvenance,
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

STATELESS_TOOL_EXECUTION = {
    "timeout": "bounded service deadline; timed-out results are never published",
    "idempotency": "optional key bound to the canonical validated request hash",
    "checkpoint_resume": "not applicable to a bounded stateless invocation",
    "provenance": "request hash, code SHA, caller data version and declared source",
}


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any]
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    timeout_seconds: float | None = Field(default=None, ge=0.001, le=60.0)

    model_config = ConfigDict(extra="forbid")


class BurnUnitClimatologyJobRequest(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=200)
    burn_ids: list[str] = Field(default_factory=list, max_length=500)
    metrics: list[str] = Field(default_factory=list, max_length=20)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")


class BurnUnitClimatologyResumeRequest(BaseModel):
    checkpoint_token: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=200)

    model_config = ConfigDict(extra="forbid")


class CheckpointedJobError(RuntimeError):
    """A catalog-scoped job failed after publishing a resumable checkpoint token."""

    def __init__(self, message: str, checkpoint_token: str) -> None:
        super().__init__(message)
        self.checkpoint_token = checkpoint_token


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for a different canonical request."""


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _IdempotencyStore:
    def __init__(self, max_entries: int = 1024) -> None:
        self.max_entries = max_entries
        self.lock = threading.Lock()
        self.rows: OrderedDict[tuple[str, str], tuple[str, ToolEnvelope]] = OrderedDict()

    def get(self, tool_name: str, key: str, request_sha256: str) -> ToolEnvelope | None:
        cache_key = (tool_name, key)
        with self.lock:
            row = self.rows.get(cache_key)
            if row is None:
                return None
            cached_hash, cached = row
            if cached_hash != request_sha256:
                raise IdempotencyConflict(
                    "idempotency key is already bound to a different validated request"
                )
            self.rows.move_to_end(cache_key)
            replay = cached.model_copy(deep=True)
            if replay.execution is not None:
                replay.execution = replay.execution.model_copy(
                    update={"replayed": True, "elapsed_ms": 0.0}
                )
            return replay

    def put(
        self,
        tool_name: str,
        key: str,
        request_sha256: str,
        envelope: ToolEnvelope,
    ) -> None:
        cache_key = (tool_name, key)
        with self.lock:
            self.rows[cache_key] = (request_sha256, envelope.model_copy(deep=True))
            self.rows.move_to_end(cache_key)
            while len(self.rows) > self.max_entries:
                self.rows.popitem(last=False)


class _JobStore:
    def __init__(self, runner: Callable[[dict[str, Any]], Any] | None) -> None:
        self.runner = runner
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="flare-tool-job")
        self.lock = threading.Lock()
        self.rows: dict[str, dict[str, Any]] = {}
        self.idempotency: dict[str, tuple[str, str]] = {}

    def submit(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None,
        parent_job_id: str | None = None,
    ) -> tuple[str, bool]:
        request_sha256 = _canonical_hash(payload)
        with self.lock:
            if idempotency_key and idempotency_key in self.idempotency:
                cached_hash, cached_job_id = self.idempotency[idempotency_key]
                if cached_hash != request_sha256:
                    raise IdempotencyConflict(
                        "job idempotency key is already bound to a different request"
                    )
                return cached_job_id, True
            job_id = uuid.uuid4().hex
            self.rows[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "request": payload,
                "request_sha256": request_sha256,
                "idempotency_key": idempotency_key,
                "parent_job_id": parent_job_id,
                "checkpoint_mode": "artifact_checkpoint",
                "created_at_utc": _utc_now(),
                "updated_at_utc": _utc_now(),
            }
            if idempotency_key:
                self.idempotency[idempotency_key] = (request_sha256, job_id)

        def run() -> None:
            with self.lock:
                self.rows[job_id].update({"status": "running", "updated_at_utc": _utc_now()})
            try:
                if self.runner is None:
                    raise RuntimeError("burn-unit climatology runner is not configured")
                result = self.runner(payload)
                with self.lock:
                    self.rows[job_id].update(
                        {"status": "completed", "result": result, "updated_at_utc": _utc_now()}
                    )
            except CheckpointedJobError as exc:
                with self.lock:
                    self.rows[job_id].update(
                        {
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                            "checkpoint_token": exc.checkpoint_token,
                            "updated_at_utc": _utc_now(),
                        }
                    )
            except Exception as exc:  # noqa: BLE001 - job state must be fail-closed
                with self.lock:
                    self.rows[job_id].update(
                        {
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                            "updated_at_utc": _utc_now(),
                        }
                    )

        self.executor.submit(run)
        return job_id, False

    def resume(
        self,
        job_id: str,
        *,
        checkpoint_token: str,
        idempotency_key: str,
    ) -> tuple[str, bool]:
        with self.lock:
            row = self.rows.get(job_id)
            if row is None:
                raise KeyError(job_id)
            if row["status"] != "failed":
                raise ValueError("only a failed job can be resumed")
            stored_checkpoint = row.get("checkpoint_token")
            if not stored_checkpoint:
                raise ValueError("failed job did not publish a checkpoint")
            if stored_checkpoint != checkpoint_token:
                raise ValueError("checkpoint token does not match the failed job")
            payload = dict(row["request"])
        payload["resume_from_checkpoint"] = checkpoint_token
        return self.submit(
            payload,
            idempotency_key=idempotency_key,
            parent_job_id=job_id,
        )

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.lock:
            row = self.rows.get(job_id)
            return dict(row) if row else None


def _service_envelope(
    envelope: ToolEnvelope,
    *,
    tool_name: str,
    request_sha256: str,
    timeout_seconds: float,
    elapsed_ms: float,
    idempotency_key: str | None,
    code_sha: str,
) -> ToolEnvelope:
    provenance_status: Literal["caller_asserted", "incomplete"] = (
        "incomplete" if envelope.data_version.strip().lower() in {"", "unknown"} else "caller_asserted"
    )
    warnings = list(envelope.warnings)
    if provenance_status == "incomplete":
        warnings.append("caller did not provide a specific data_version")
    return envelope.model_copy(
        update={
            "tool_name": tool_name,
            "trace_id": envelope.trace_id or uuid.uuid4().hex,
            "warnings": warnings,
            "provenance": ToolProvenance(
                status=provenance_status,
                request_sha256=request_sha256,
                code_sha=code_sha,
                source_references=[envelope.source],
            ),
            "execution": ToolExecution(
                mode="service",
                timeout_seconds=timeout_seconds,
                elapsed_ms=elapsed_ms,
                idempotency_key=idempotency_key,
                replayed=False,
                checkpoint_mode="not_applicable_stateless",
            ),
        }
    )


def _error_envelope(
    *,
    tool_name: str,
    data_version: str,
    request_sha256: str,
    timeout_seconds: float,
    elapsed_ms: float,
    idempotency_key: str | None,
    code: str,
    message: str,
    retryable: bool,
    code_sha: str,
) -> ToolEnvelope:
    return _service_envelope(
        ToolEnvelope(
            tool_name=tool_name,
            status="error",
            data_version=data_version,
            source=f"{tool_name} deterministic domain tool",
            constraints=["no result is published after a failed or timed-out invocation"],
            warnings=[],
            result=None,
            error=ToolError(code=code, message=message, retryable=retryable),
        ),
        tool_name=tool_name,
        request_sha256=request_sha256,
        timeout_seconds=timeout_seconds,
        elapsed_ms=elapsed_ms,
        idempotency_key=idempotency_key,
        code_sha=code_sha,
    )


def create_app(
    *,
    climatology_runner: Callable[[dict[str, Any]], Any] | None = None,
    tool_registry: Mapping[str, tuple[type[BaseModel], Callable[..., ToolEnvelope]]] | None = None,
    default_tool_timeout_seconds: float = 30.0,
):
    try:
        from fastapi import FastAPI, HTTPException, Response
    except ImportError as exc:
        raise RuntimeError("FastAPI is unavailable; install the 'serve' extra") from exc

    if not 0.001 <= default_tool_timeout_seconds <= 60.0:
        raise ValueError("default_tool_timeout_seconds must be between 0.001 and 60")
    registry = dict(tool_registry or TOOL_REGISTRY)
    unknown_registry_names = sorted(set(registry) - set(tool_schemas()))
    if unknown_registry_names:
        raise ValueError(f"tool registry contains unknown schemas: {unknown_registry_names}")
    jobs = _JobStore(climatology_runner)
    code_version = git_sha()
    idempotency = _IdempotencyStore()
    tool_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="flare-tool")
    counters: dict[str, int] = defaultdict(int)
    latencies: dict[str, list[float]] = defaultdict(list)
    metric_lock = threading.Lock()
    app = FastAPI(
        title="FLARE Trusted Burn-window Tool Service",
        version="0.3.0",
        description=(
            "Typed deterministic tools. The service rejects undeclared fields and never lets "
            "a language model modify prescriptions or execute arbitrary expressions."
        ),
    )

    def record(tool_name: str, status: str, latency_ms: float) -> None:
        with metric_lock:
            counters[f"{tool_name}:{status}"] += 1
            latencies[tool_name].append(latency_ms)

    @app.get("/api/tools")
    def list_tools() -> dict[str, Any]:
        schemas = tool_schemas()
        return {
            "tools": {
                name: {
                    "input_schema": schemas[name],
                    "output_schema": ToolEnvelope.model_json_schema(),
                    "execution": STATELESS_TOOL_EXECUTION,
                }
                for name in sorted(registry)
            }
        }

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
        try:
            parsed = request_model.model_validate(request.arguments)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"reason": "schema_validation", "errors": exc.errors()},
            ) from exc
        validated_arguments = parsed.model_dump(mode="json")
        request_sha256 = _canonical_hash(validated_arguments)
        if request.idempotency_key:
            try:
                cached = idempotency.get(tool_name, request.idempotency_key, request_sha256)
            except IdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if cached is not None:
                record(tool_name, "replayed", 0.0)
                return cached.model_dump(mode="json")

        timeout_seconds = request.timeout_seconds or default_tool_timeout_seconds
        started = time.perf_counter()
        future = tool_executor.submit(function, **parsed.model_dump())
        try:
            envelope = future.result(timeout=timeout_seconds)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            envelope = _service_envelope(
                envelope,
                tool_name=tool_name,
                request_sha256=request_sha256,
                timeout_seconds=timeout_seconds,
                elapsed_ms=elapsed_ms,
                idempotency_key=request.idempotency_key,
                code_sha=code_version,
            )
        except FutureTimeoutError:
            future.cancel()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            envelope = _error_envelope(
                tool_name=tool_name,
                data_version=str(validated_arguments.get("data_version", "unknown")),
                request_sha256=request_sha256,
                timeout_seconds=timeout_seconds,
                elapsed_ms=elapsed_ms,
                idempotency_key=request.idempotency_key,
                code="tool_timeout",
                message=f"tool exceeded the {timeout_seconds:.3f}s service deadline",
                retryable=True,
                code_sha=code_version,
            )
        except Exception as exc:  # noqa: BLE001 - result publication must fail closed
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            envelope = _error_envelope(
                tool_name=tool_name,
                data_version=str(validated_arguments.get("data_version", "unknown")),
                request_sha256=request_sha256,
                timeout_seconds=timeout_seconds,
                elapsed_ms=elapsed_ms,
                idempotency_key=request.idempotency_key,
                code=(
                    "domain_validation_error"
                    if isinstance(exc, (TypeError, ValueError))
                    else "tool_error"
                ),
                message=f"{type(exc).__name__}: {str(exc)[:500]}",
                retryable=False,
                code_sha=code_version,
            )
        record(tool_name, envelope.status, elapsed_ms)
        if request.idempotency_key:
            idempotency.put(tool_name, request.idempotency_key, request_sha256, envelope)
        return envelope.model_dump(mode="json")

    @app.post("/api/jobs/burn-unit-climatology", status_code=202)
    def submit_climatology(request: BurnUnitClimatologyJobRequest) -> dict[str, Any]:
        payload = request.model_dump(exclude={"idempotency_key"})
        try:
            job_id, replayed = jobs.submit(
                payload,
                idempotency_key=request.idempotency_key,
            )
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"job_id": job_id, "status": "queued", "replayed": replayed}

    @app.post("/api/jobs/{job_id}:resume", status_code=202)
    def resume_climatology(
        job_id: str,
        request: BurnUnitClimatologyResumeRequest,
    ) -> dict[str, Any]:
        try:
            resumed_job_id, replayed = jobs.resume(
                job_id,
                checkpoint_token=request.checkpoint_token,
                idempotency_key=request.idempotency_key,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="job not found") from exc
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"job_id": resumed_job_id, "status": "queued", "replayed": replayed}

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
            lines.append("# TYPE flare_tool_latency_ms gauge")
            for tool, values in sorted(latencies.items()):
                if not values:
                    continue
                ordered = sorted(values)
                for label, quantile in (("p50", 0.50), ("p95", 0.95)):
                    index = min(len(ordered) - 1, int(quantile * len(ordered)))
                    lines.append(
                        f'flare_tool_latency_ms{{tool="{tool}",quantile="{label}"}} '
                        f"{ordered[index]:.6f}"
                    )
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    return app
