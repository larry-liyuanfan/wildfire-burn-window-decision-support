from __future__ import annotations

import time
from typing import Any

from fastapi.testclient import TestClient

from burnwindows.models import ToolEnvelope
from burnwindows.service import TOOL_REGISTRY, CheckpointedJobError, create_app
from burnwindows.tool_benchmark import TOOL_NAMES, fixture_payloads


def _payload() -> dict[str, Any]:
    return fixture_payloads(24)["find_burn_windows"]


def _poll(client: TestClient, job_id: str) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for _ in range(100):
        row = client.get(f"/api/jobs/{job_id}").json()
        if row["status"] in {"completed", "failed"}:
            return row
        time.sleep(0.005)
    raise AssertionError("job did not finish")


def test_all_six_tools_publish_one_output_and_execution_contract() -> None:
    body = TestClient(create_app()).get("/api/tools").json()["tools"]
    assert tuple(sorted(body)) == TOOL_NAMES
    for contract in body.values():
        assert contract["input_schema"]["type"] == "object"
        assert contract["output_schema"] == ToolEnvelope.model_json_schema()
        assert "request hash" in contract["execution"]["idempotency"]
        assert contract["execution"]["checkpoint_resume"].startswith("not applicable")


def test_idempotency_replays_same_request_and_rejects_key_rebinding() -> None:
    client = TestClient(create_app())
    first = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": _payload(), "idempotency_key": "same-request"},
    )
    replay = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": _payload(), "idempotency_key": "same-request"},
    )
    changed = _payload()
    changed["min_duration_hours"] = 3
    conflict = client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": changed, "idempotency_key": "same-request"},
    )
    assert first.status_code == 200
    assert replay.json()["trace_id"] == first.json()["trace_id"]
    assert replay.json()["execution"]["replayed"] is True
    assert conflict.status_code == 409


def test_service_timeout_fails_closed_then_accepts_clean_retry() -> None:
    request_model, function = TOOL_REGISTRY["find_burn_windows"]

    def slow_tool(**arguments: Any):
        time.sleep(0.03)
        return function(**arguments)

    registry = dict(TOOL_REGISTRY)
    registry["find_burn_windows"] = (request_model, slow_tool)
    timeout_client = TestClient(create_app(tool_registry=registry, default_tool_timeout_seconds=0.005))
    timed_out = timeout_client.post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": _payload(), "idempotency_key": "timed-out"},
    ).json()
    recovered = TestClient(create_app()).post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": _payload(), "idempotency_key": "clean-retry"},
    ).json()
    assert timed_out["status"] == "error"
    assert timed_out["result"] is None
    assert timed_out["error"]["code"] == "tool_timeout"
    assert timed_out["error"]["retryable"] is True
    assert recovered["status"] == "ok"


def test_domain_failure_is_a_machine_readable_error_envelope() -> None:
    payload = _payload()
    payload["data"]["temperature_c"] = [20.0]
    response = TestClient(create_app()).post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": payload},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "error"
    assert response.json()["error"]["code"] == "domain_validation_error"


def test_service_marks_unspecified_data_provenance_incomplete() -> None:
    payload = _payload()
    payload["data_version"] = "unknown"
    response = TestClient(create_app()).post(
        "/api/tools/find_burn_windows:invoke",
        json={"arguments": payload},
    ).json()
    assert response["provenance"]["status"] == "incomplete"
    assert len(response["provenance"]["request_sha256"]) == 64
    assert "specific data_version" in response["warnings"][-1]


def test_failed_artifact_job_resumes_only_from_its_exact_checkpoint() -> None:
    def runner(arguments: dict[str, Any]) -> dict[str, Any]:
        if arguments.get("resume_from_checkpoint") != "checkpoint-24h":
            raise CheckpointedJobError("controlled interruption", "checkpoint-24h")
        return {"resumed": True}

    client = TestClient(create_app(climatology_runner=runner))
    submitted = client.post(
        "/api/jobs/burn-unit-climatology",
        json={"artifact_id": "catalog-v1", "idempotency_key": "job-1"},
    ).json()
    failed = _poll(client, submitted["job_id"])
    wrong = client.post(
        f"/api/jobs/{submitted['job_id']}:resume",
        json={"checkpoint_token": "wrong", "idempotency_key": "job-2"},
    )
    resumed = client.post(
        f"/api/jobs/{submitted['job_id']}:resume",
        json={"checkpoint_token": "checkpoint-24h", "idempotency_key": "job-2"},
    ).json()
    completed = _poll(client, resumed["job_id"])
    assert failed["checkpoint_token"] == "checkpoint-24h"
    assert wrong.status_code == 422
    assert completed["status"] == "completed"
    assert completed["parent_job_id"] == submitted["job_id"]


def test_fixed_load_fixture_covers_exactly_the_six_public_tools() -> None:
    payloads = fixture_payloads(24)
    assert tuple(sorted(payloads)) == TOOL_NAMES
    assert all(payload["data_version"] == "fixed-load-fixture-v1" for payload in payloads.values())
