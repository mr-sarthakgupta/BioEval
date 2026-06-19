#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

import requests


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ask the benchmark data-agent to place a dataset in /workspace/data."
    )
    parser.add_argument("question", help="Describe the dataset or experiment you want.")
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
    response = requests.post(args.agent_url, json=payload, timeout=600)
    response.raise_for_status()
    result = response.json()
    print(json.dumps(result, indent=2))

    if result.get("status") == "denied":
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
