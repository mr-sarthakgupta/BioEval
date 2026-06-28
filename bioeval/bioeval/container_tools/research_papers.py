#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

import requests

from bioeval_tool_common import append_tool_event, truncate


ALLOWED_OPERATIONS = {"search", "snippet_search"}
DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "http://data-agent:8765/request-data")


def proxy_url(path: str) -> str:
    return DATA_AGENT_URL.rsplit("/", 1)[0] + path


def main() -> int:
    parser = argparse.ArgumentParser(description="Constrained literature search for background methods and datasets.")
    parser.add_argument("operation", choices=sorted(ALLOWED_OPERATIONS))
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    request = vars(args)
    try:
        resp = requests.post(
            proxy_url("/tools/research-papers"),
            json={"operation": args.operation, "query": args.query, "limit": args.limit},
            timeout=90,
        )
        resp.raise_for_status()
        response = resp.json()
        if response.get("status") == "denied":
            append_tool_event("research_papers", request, response, "denied")
            print(response.get("error", "Denied by blind-setup search filter."), file=sys.stderr)
            return 2
        output = truncate(response.get("content", "No papers found."))
        response["content"] = output
        append_tool_event("research_papers", request, response, "ok")
        print(output)
        return 0
    except Exception as exc:
        response = {"error": str(exc)}
        append_tool_event("research_papers", request, response, "error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
