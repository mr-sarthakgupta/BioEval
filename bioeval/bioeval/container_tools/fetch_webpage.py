#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys

import requests

from bioeval_tool_common import (
    REFERENCE_DIR,
    append_tool_event,
    relative_workspace_path,
    truncate,
)

DATA_AGENT_URL = os.getenv("DATA_AGENT_URL", "http://data-agent:8765/request-data")


def proxy_url(path: str) -> str:
    return DATA_AGENT_URL.rsplit("/", 1)[0] + path


def slug(url: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", url.lower()).strip("_")
    digest = hashlib.md5(url.encode()).hexdigest()[:8]
    return f"{digest}_{cleaned[-70:]}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch a webpage into /workspace/reference.")
    parser.add_argument("url")
    parser.add_argument("--max-chars", type=int, default=80000)
    args = parser.parse_args()
    request = vars(args)
    try:
        resp = requests.post(
            proxy_url("/tools/fetch-webpage"),
            json={"url": args.url, "max_chars": args.max_chars},
            timeout=90,
        )
        resp.raise_for_status()
        result = resp.json()
        if result.get("status") == "denied":
            append_tool_event("fetch_webpage", request, result, "denied")
            print(f"Denied: {result.get('error', 'blocked by blind-setup fetch filter')}", file=sys.stderr)
            return 2
        if result.get("status") == "error":
            raise ValueError(result.get("error", "fetch failed"))
        text = truncate(result.get("text", ""), args.max_chars)
        fetched_url = result.get("url", args.url)
        content_type = result.get("content_type", "")
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        path = REFERENCE_DIR / f"web_{slug(fetched_url)}.txt"
        path.write_text(
            f"# Fetched page: {fetched_url}\n# Content-Type: {content_type}\n\n{text}\n",
            encoding="utf-8",
            errors="replace",
        )
        rel = relative_workspace_path(path)
        response = {"saved_path": rel, "url": fetched_url, "chars": len(text)}
        append_tool_event("fetch_webpage", request, response, "ok")
        print(f"Saved to: {rel}")
        print(f"Use: read_file {rel}")
        return 0
    except Exception as exc:
        response = {"error": str(exc)}
        append_tool_event("fetch_webpage", request, response, "error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
