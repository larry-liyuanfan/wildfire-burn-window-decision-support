"""Fixed-load benchmark for the six stateless FLARE domain tools.

The benchmark uses deterministic fixtures and a loopback FastAPI TestClient. It
is evidence about the local tool boundary, not a production SLA or a field-data
quality result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .manifest import git_sha, write_json

TOOL_NAMES = (
    "compare_threshold_scenarios",
    "derive_fuel_inputs",
    "explain_limiting_factors",
    "find_burn_windows",
    "get_region_trend",
    "optimize_burn_schedule",
)


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1)
    return ordered[max(0, index)]


def _fixture_prescription() -> dict[str, Any]:
    return {
        "burn_class": "fixed-load-fixture",
        "conditions": [
            {
                "field": "Temperature",
                "variable": "temperature_c",
                "unit": "degC",
                "lower": {"value": 15.0, "inclusive": True},
                "upper": {"value": 25.0, "inclusive": True},
                "source_text": "fixture 15-25 degC",
            },
            {
                "field": "RelativeHumidity",
                "variable": "relative_humidity_pct",
                "unit": "%",
                "lower": {"value": 35.0, "inclusive": True},
                "upper": {"value": 60.0, "inclusive": True},
                "source_text": "fixture 35-60 percent",
            },
        ],
        "source": "deterministic benchmark fixture; not an operational prescription",
    }


def fixture_payloads(hours: int = 168) -> dict[str, dict[str, Any]]:
    if hours < 24:
        raise ValueError("hours must be at least 24")
    start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    times = [(start + timedelta(hours=index)).isoformat() for index in range(hours)]
    temperature = [20.0 + 8.0 * math.sin(index / 24.0 * math.tau) for index in range(hours)]
    humidity = [52.0 - 20.0 * math.sin(index / 24.0 * math.tau) for index in range(hours)]
    wind = [12.0 + float(index % 7) for index in range(hours)]
    precipitation = [0.4 if index % 53 == 0 else 0.0 for index in range(hours)]
    common = {
        "times": times,
        "data": {
            "temperature_c": temperature,
            "relative_humidity_pct": humidity,
        },
        "prescription": _fixture_prescription(),
        "data_version": "fixed-load-fixture-v1",
    }
    candidates = []
    for index in range(12):
        candidate_start = start + timedelta(hours=index * 3)
        candidates.append(
            {
                "id": f"candidate-{index:02d}",
                "region": "fixture-east" if index % 2 == 0 else "fixture-west",
                "start": candidate_start.isoformat(),
                "end": (candidate_start + timedelta(hours=3 + index % 3)).isoformat(),
                "area_hectares": float(5 + index),
                "robustness": 0.75 + 0.02 * (index % 5),
                "quality": float(index % 4),
                "crew_demand": 1 + index % 2,
                "mobilisation_cost": float(index % 3),
            }
        )
    return {
        "find_burn_windows": {**common, "min_duration_hours": 2, "location": "fixture"},
        "explain_limiting_factors": common,
        "compare_threshold_scenarios": {
            **common,
            "scenarios": {
                "temperature_wider": {"Temperature": 2.0},
                "humidity_wider": {"RelativeHumidity": 5.0},
            },
        },
        "get_region_trend": {
            "years": list(range(1973, 2024)),
            "suitable_rates": [0.03 + 0.0001 * index for index in range(51)],
            "region": "fixture-district",
            "block_size": 5,
            "bootstrap_samples": 100,
            "data_version": "fixed-load-fixture-v1",
        },
        "optimize_burn_schedule": {
            "candidates": candidates,
            "crew_capacity": 3,
            "min_duration_hours": 2.0,
            "daily_capacity": 4,
            "data_version": "fixed-load-fixture-v1",
        },
        "derive_fuel_inputs": {
            "temperature_c": [max(1.0, value) for value in temperature],
            "relative_humidity_pct": [min(100.0, max(1.0, value)) for value in humidity],
            "wind_10m_kmh": wind,
            "precipitation_mm": precipitation,
            "wind_reduction_factor": 0.33,
            "rain_guard_mm": 0.2,
            "data_version": "fixed-load-fixture-v1",
        },
    }


def _stable_result_hash(payload: dict[str, Any]) -> str:
    stable = {
        key: payload.get(key)
        for key in ("status", "data_version", "source", "constraints", "warnings", "result", "error")
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _worker(tool_name: str, *, repetitions: int, warmup: int, hours: int) -> dict[str, Any]:
    try:
        import psutil
        from fastapi.testclient import TestClient
    except ImportError as exc:  # pragma: no cover - explicit benchmark dependency gate
        raise RuntimeError("install the dev and serve extras before benchmarking") from exc

    from .service import create_app

    if tool_name not in TOOL_NAMES:
        raise ValueError(f"unknown benchmark tool: {tool_name}")
    payload = fixture_payloads(hours)[tool_name]
    client = TestClient(create_app(default_tool_timeout_seconds=30.0))
    for index in range(warmup):
        response = client.post(
            f"/api/tools/{tool_name}:invoke",
            json={"arguments": payload, "idempotency_key": f"warmup-{tool_name}-{index}"},
        )
        response.raise_for_status()
        if response.json()["status"] not in {"ok", "partial"}:
            raise RuntimeError(f"warmup failed for {tool_name}: {response.json()}")

    process = psutil.Process(os.getpid())
    rss_before = int(process.memory_info().rss)
    peak_rss = rss_before
    stop_sampling = threading.Event()

    def sample_rss() -> None:
        nonlocal peak_rss
        while not stop_sampling.is_set():
            peak_rss = max(peak_rss, int(process.memory_info().rss))
            stop_sampling.wait(0.001)

    sampler = threading.Thread(target=sample_rss, daemon=True)
    sampler.start()
    tracemalloc.start()
    round_trip_ms: list[float] = []
    tool_elapsed_ms: list[float] = []
    result_hashes: set[str] = set()
    success_count = 0
    try:
        for index in range(repetitions):
            started = time.perf_counter()
            response = client.post(
                f"/api/tools/{tool_name}:invoke",
                json={
                    "arguments": payload,
                    "idempotency_key": f"measured-{tool_name}-{index}",
                },
            )
            round_trip_ms.append((time.perf_counter() - started) * 1000.0)
            response.raise_for_status()
            body = response.json()
            if body["status"] in {"ok", "partial"}:
                success_count += 1
            result_hashes.add(_stable_result_hash(body))
            tool_elapsed_ms.append(float(body["execution"]["elapsed_ms"]))
    finally:
        _, python_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        stop_sampling.set()
        sampler.join(timeout=1.0)
        peak_rss = max(peak_rss, int(process.memory_info().rss))

    return {
        "tool": tool_name,
        "repetitions": repetitions,
        "success_count": success_count,
        "success_rate": success_count / repetitions,
        "deterministic_result_hash_count": len(result_hashes),
        "latency_ms": {
            "service_execution_p50": statistics.median(tool_elapsed_ms),
            "service_execution_p95": _percentile(tool_elapsed_ms, 0.95),
            "loopback_round_trip_p50": statistics.median(round_trip_ms),
            "loopback_round_trip_p95": _percentile(round_trip_ms, 0.95),
        },
        "memory_bytes": {
            "process_rss_before": rss_before,
            "process_peak_rss": peak_rss,
            "process_peak_rss_delta": max(0, peak_rss - rss_before),
            "python_tracemalloc_peak": int(python_peak),
        },
    }


def _poll_job(client: Any, job_id: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for _ in range(200):
        row = client.get(f"/api/jobs/{job_id}").json()
        if row["status"] in {"completed", "failed"}:
            return row
        time.sleep(0.005)
    raise RuntimeError(f"job did not finish: {job_id}")


def failure_recovery_checks() -> list[dict[str, Any]]:
    from fastapi.testclient import TestClient

    from .service import TOOL_REGISTRY, CheckpointedJobError, create_app

    payload = fixture_payloads(24)["find_burn_windows"]
    client = TestClient(create_app())
    invalid = dict(payload)
    invalid["arbitrary_expression"] = "forbidden"
    rejected = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": invalid},
    )
    corrected = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": payload, "idempotency_key": "fixture-recovery"},
    )
    replay = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": payload, "idempotency_key": "fixture-recovery"},
    )
    changed = dict(payload)
    changed["min_duration_hours"] = 3
    conflict = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": changed, "idempotency_key": "fixture-recovery"},
    )

    original_model, original_function = TOOL_REGISTRY["find_burn_windows"]

    def slow_tool(**arguments: Any):
        time.sleep(0.03)
        return original_function(**arguments)

    timeout_registry = dict(TOOL_REGISTRY)
    timeout_registry["find_burn_windows"] = (original_model, slow_tool)
    timeout_client = TestClient(
        create_app(tool_registry=timeout_registry, default_tool_timeout_seconds=0.005)
    )
    timed_out = timeout_client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": payload, "idempotency_key": "fixture-timeout"},
    )
    recovered_after_timeout = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": payload, "idempotency_key": "fixture-after-timeout"},
    )

    def checkpoint_runner(arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments.get("resume_from_checkpoint") != "fixture-checkpoint-24h":
            raise CheckpointedJobError("controlled fixture interruption", "fixture-checkpoint-24h")
        return {"resumed": True, "artifact_id": arguments["artifact_id"]}

    job_client = TestClient(create_app(climatology_runner=checkpoint_runner))
    submitted = job_client.post(
        "/api/jobs/burn-unit-climatology",
        json={"artifact_id": "fixture-artifact", "idempotency_key": "fixture-job"},
    ).json()
    failed = _poll_job(job_client, submitted["job_id"])
    resumed = job_client.post(
        f"/api/jobs/{submitted['job_id']}:resume",
        json={
            "checkpoint_token": "fixture-checkpoint-24h",
            "idempotency_key": "fixture-job-resume",
        },
    ).json()
    completed = _poll_job(job_client, resumed["job_id"])

    checks = [
        {
            "case": "undeclared_field_rejected_then_corrected",
            "passed": rejected.status_code == 422 and corrected.json()["status"] == "ok",
        },
        {
            "case": "same_key_same_request_replayed",
            "passed": replay.status_code == 200 and replay.json()["execution"]["replayed"] is True,
        },
        {
            "case": "same_key_different_request_conflicts",
            "passed": conflict.status_code == 409,
        },
        {
            "case": "deadline_fails_closed",
            "passed": timed_out.json()["error"]["code"] == "tool_timeout",
        },
        {
            "case": "corrected_request_succeeds_after_timeout",
            "passed": recovered_after_timeout.json()["status"] == "ok",
        },
        {
            "case": "artifact_job_resumes_from_exact_checkpoint",
            "passed": failed["status"] == "failed" and completed["status"] == "completed",
        },
    ]
    if not all(item["passed"] for item in checks):
        raise RuntimeError(f"failure-recovery gate failed: {checks}")
    return checks


def run_benchmark(
    *,
    output: Path,
    repetitions: int = 50,
    warmup: int = 3,
    hours: int = 168,
) -> dict[str, Any]:
    if repetitions < 1 or warmup < 0:
        raise ValueError("repetitions must be positive and warmup cannot be negative")
    results = []
    for tool_name in TOOL_NAMES:
        command = [
            sys.executable,
            "-m",
            "burnwindows.tool_benchmark",
            "--worker",
            tool_name,
            "--repetitions",
            str(repetitions),
            "--warmup",
            str(warmup),
            "--hours",
            str(hours),
        ]
        raw = subprocess.check_output(command, text=True)
        results.append(json.loads(raw))
    record = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "benchmark_kind": "offline-domain-tool-fixture",
        "boundary": (
            "Loopback deterministic-fixture benchmark only; not a production SLA, autonomous "
            "Agent evaluation, VicClim6 quality result, field validation or safety evidence."
        ),
        "implementation_git_sha": git_sha(),
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "workload": {
            "hourly_points_for_array_tools": hours,
            "annual_points_for_trend": 51,
            "bootstrap_samples_for_trend": 100,
            "schedule_candidates": 12,
            "warmup_calls_per_tool": warmup,
            "measured_calls_per_tool": repetitions,
            "request_fixture_version": "fixed-load-fixture-v1",
        },
        "tools": results,
        "failure_recovery": failure_recovery_checks(),
    }
    write_json(output, record)
    return record


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repetitions", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--hours", type=int, default=168)
    parser.add_argument("--worker", choices=TOOL_NAMES)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.worker:
        print(
            json.dumps(
                _worker(
                    args.worker,
                    repetitions=args.repetitions,
                    warmup=args.warmup,
                    hours=args.hours,
                )
            )
        )
        return 0
    if args.output is None:
        raise SystemExit("--output is required unless --worker is used")
    print(
        json.dumps(
            run_benchmark(
                output=args.output,
                repetitions=args.repetitions,
                warmup=args.warmup,
                hours=args.hours,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
