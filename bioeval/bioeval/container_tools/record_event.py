#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tool_log_path() -> Path:
    return Path(os.getenv("BIOEVAL_TOOL_LOG", "/submit/tool_calls.jsonl"))


def append_event(record: dict[str, Any], path: Path | None = None) -> None:
    target = path or tool_log_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a structured rollout event.")
    parser.add_argument("--type", default="note", help="Event type, e.g. note, command, observation.")
    parser.add_argument("--text", default="", help="Human-readable event text.")
    parser.add_argument("--json", dest="json_payload", help="Optional JSON object payload.")
    parser.add_argument("--log-file", type=Path, default=tool_log_path())
    args = parser.parse_args()

    payload: dict[str, Any] | None = None
    if args.json_payload:
        try:
            raw_payload = json.loads(args.json_payload)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON payload: {exc}", file=sys.stderr)
            return 1
        if not isinstance(raw_payload, dict):
            print("--json must be a JSON object", file=sys.stderr)
            return 1
        payload = raw_payload

    append_event(
        {
            "event": args.type,
            "timestamp": utc_now(),
            "run_id": os.getenv("BIOEVAL_RUN_ID"),
            "text": args.text,
            "payload": payload,
        },
        args.log_file,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
