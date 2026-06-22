#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_tool_event(record: dict) -> None:
    path = Path(os.getenv("BIOEVAL_TOOL_LOG", "/submit/tool_calls.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ask the benchmark data-agent to place a specific dataset in /workspace/data."
    )
    parser.add_argument(
        "question",
        help=(
            "Specifically describe the measurement/data type and scope you want; broad "
            "inventory requests may be denied."
        ),
    )
    parser.add_argument("--modality", action="append", default=[], help="Optional desired modality.")
    parser.add_argument("--max-bytes", type=int, default=200_000_000)
    parser.add_argument(
        "--agent-url",
        default=os.getenv("DATA_AGENT_URL", "http://data-agent:8765/request-data"),
    )
    args = parser.parse_args()

    payload = {
        "question": args.question,
        "desired_modalities": args.modality,
        "max_bytes": args.max_bytes,
    }
    event = {
        "event": "tool_call",
        "tool": "request_data",
        "timestamp": utc_now(),
        "run_id": os.getenv("BIOEVAL_RUN_ID"),
        "request": payload,
    }
    try:
        response = requests.post(args.agent_url, json=payload, timeout=600)
        response.raise_for_status()
        result = response.json()
        event["response"] = result
        event["status"] = "ok"
    except Exception as exc:
        event["status"] = "error"
        event["error"] = str(exc)
        append_tool_event(event)
        raise
    append_tool_event(event)
    print(json.dumps(result, indent=2))

    if result.get("status") == "denied":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
