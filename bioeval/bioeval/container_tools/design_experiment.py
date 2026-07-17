#!/usr/bin/env python3
"""Submit one structured experiment for simulated execution."""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

from bioeval_tool_common import append_tool_event


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Submit a reproducible experiment design to the experiment-agent."
    )
    parser.add_argument("spec_json", help="Complete ExperimentRequest JSON object.")
    parser.add_argument(
        "--agent-url",
        default=os.getenv(
            "EXPERIMENT_AGENT_URL",
            "http://experiment-agent:8765/experiments",
        ),
    )
    args = parser.parse_args()
    try:
        payload = json.loads(args.spec_json)
    except json.JSONDecodeError as exc:
        parser.error(f"spec_json is not valid JSON: {exc}")

    try:
        response = requests.post(args.agent_url, json=payload, timeout=900)
        response.raise_for_status()
        result = response.json()
    except Exception as exc:
        append_tool_event(
            "design_experiment",
            payload,
            {"error": str(exc)},
            "error",
        )
        raise
    append_tool_event("design_experiment", payload, result, "ok")
    print(json.dumps(result, indent=2))

    validation_status = (result.get("validation") or {}).get("status")
    if validation_status != "feasible":
        return 2
    if result.get("execution_status") not in {"completed", "partially_completed"}:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
