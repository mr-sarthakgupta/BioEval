#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys

import requests

from bioeval_tool_common import append_tool_event, truncate

DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "http://data-agent:8765/request-data")


def proxy_url(path: str) -> str:
    return DATA_AGENT_URL.rsplit("/", 1)[0] + path


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the web with blind-setup constraints.")
    parser.add_argument("query")
    parser.add_argument("--allowed-domain", action="append", default=[])
    parser.add_argument("--blocked-domain", action="append", default=[])
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    request = vars(args)
    try:
        resp = requests.post(
            proxy_url("/tools/web-search"),
            json={
                "query": args.query,
                "limit": args.limit,
                "allowed_domain": args.allowed_domain,
                "blocked_domain": args.blocked_domain,
            },
            timeout=90,
        )
        resp.raise_for_status()
        response = resp.json()
        if response.get("status") == "denied":
            append_tool_event("web_search", request, response, "denied")
            print(response.get("error", "No results found."), file=sys.stderr)
            return 2
        output = truncate(response.get("content", "No search results."))
        response["content"] = output
        append_tool_event("web_search", request, response, "ok")
        print(output)
        return 0
    except Exception as exc:
        response = {"error": str(exc)}
        append_tool_event("web_search", request, response, "error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
