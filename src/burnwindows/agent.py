"""Controlled function-selection adapter for Model Studio and local contract tests."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .tools import tool_schemas


@dataclass(frozen=True, slots=True)
class ToolPlan:
    tool_name: str
    arguments: dict[str, Any]


class ModelStudioFunctionPlanner:
    def __init__(self, model: str = "qwen3.7-plus", timeout_seconds: float = 30.0) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds

    def plan(self, question: str) -> ToolPlan:
        api_key = os.getenv("DASHSCOPE_API_KEY")
        base_url = os.getenv("MODEL_STUDIO_BASE_URL")
        if not api_key or not base_url:
            raise RuntimeError(
                "DASHSCOPE_API_KEY and MODEL_STUDIO_BASE_URL are required for function planning"
            )
        tools = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Deterministic FLARE domain calculation",
                    "parameters": schema,
                },
            }
            for name, schema in sorted(tool_schemas().items())
        ]
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Select exactly one declared tool and fill only declared JSON fields. "
                            "Never modify prescriptions or emit SQL, Python, Dask, or solver code."
                        ),
                    },
                    {"role": "user", "content": question},
                ],
                "tools": tools,
                "tool_choice": "required",
                "temperature": 0,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            base_url.rstrip("/") + "/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Model Studio function planning failed ({exc.code}): {detail[:500]}") from exc
        calls = payload["choices"][0]["message"].get("tool_calls", [])
        if len(calls) != 1:
            raise RuntimeError("planner must return exactly one tool call")
        function = calls[0]["function"]
        name = str(function["name"])
        schemas = tool_schemas()
        if name not in schemas:
            raise RuntimeError("planner selected an undeclared tool")
        arguments = json.loads(function["arguments"])
        unexpected = set(arguments) - set(schemas[name].get("properties", {}))
        if unexpected:
            raise RuntimeError("planner emitted undeclared arguments")
        return ToolPlan(name, arguments)

