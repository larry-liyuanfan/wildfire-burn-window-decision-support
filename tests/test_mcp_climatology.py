"""Protocol tests are synthetic fixtures; the remote demo uses the real compact."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

pytest.importorskip("mcp")

from test_burn_unit_climatology import _full_compact_artifact

from burnwindows.burn_unit_climatology import publish_compact_artifact
from burnwindows.mcp_server import MCPClimatologyRequest
from burnwindows.service import create_app

REQUEST = {
    "artifact_id": "compact-v1",
    "burn_ids": ["burn-000"],
    "year_start": 2020,
    "year_end": 2020,
}


def test_stdio_real_client_roundtrip_with_fixture(tmp_path):
    source = tmp_path / "fixture.json"
    source.write_text(json.dumps(_full_compact_artifact()), encoding="utf-8")
    publication = publish_compact_artifact(
        source, output_dir=tmp_path / "published", artifact_id="compact-v1"
    )
    root = Path(__file__).resolve().parents[1]
    output = tmp_path / "redacted.json"
    subprocess.run(
        [
            sys.executable,
            str(root / "scripts/demo_mcp_climatology.py"),
            "--artifact-catalog",
            publication["catalog_path"],
            "--artifact-id",
            "compact-v1",
            "--burn-id",
            "burn-000",
            "--evidence-kind",
            "synthetic-contract-fixture",
            "--output",
            str(output),
        ],
        cwd=root,
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        check=True,
        timeout=60,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["tools_call_roundtrips"] == 6
    assert report["repeated_result_identical"]
    assert report["records_exported"] is False
    assert all("records" not in case for case in report["cases"])


@pytest.mark.parametrize(
    "change",
    [
        {"burn_ids": []},
        {"burn_ids": [" "]},
        {"burn_ids": ["burn-000"] * 2},
        {"year_end": 2019},
        {"year_start": 2010},
        {"year_start": "2020"},
        {"artifact_path": "forbidden.json"},
    ],
)
def test_mcp_schema_is_bounded_and_strict(change):
    with pytest.raises(ValidationError):
        MCPClimatologyRequest.model_validate({**REQUEST, **change})


def test_unavailable_fastapi_query_is_not_artifact_verified():
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/tools/get_burn_unit_climatology:invoke", json={"arguments": REQUEST}
        )
    value = response.json()
    assert value["status"] == "error" and value["result"] is None
    assert value["provenance"]["status"] == "incomplete"
