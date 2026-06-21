#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main() -> int:
    parser = argparse.ArgumentParser(description="Append a shell command event to the run log.")
    parser.add_argument("--command", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--status", type=int, default=0, help="Exit status before this command runs.")
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path(os.getenv("BIOEVAL_SHELL_COMMAND_LOG", "/submit/shell_commands.jsonl")),
    )
    args = parser.parse_args()

    args.log_file.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event": "shell_command",
        "timestamp": utc_now(),
        "run_id": os.getenv("BIOEVAL_RUN_ID"),
        "cwd": args.cwd,
        "command": args.command,
        "previous_exit_status": args.status,
    }
    with args.log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
