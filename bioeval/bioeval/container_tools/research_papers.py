#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import time
import sys
from urllib.parse import urlencode

import requests

from bioeval_tool_common import append_tool_event, deny_leaky_query, truncate


ALLOWED_OPERATIONS = {"search", "snippet_search"}
S2_API = "https://api.semanticscholar.org"
S2_API_KEY = os.getenv("S2_API_KEY")
S2_HEADERS = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}


def s2_get(path: str, params: dict, *, timeout: int = 20) -> tuple[dict | None, str | None]:
    """Semantic Scholar GET with SkyDiscover-style retry behavior."""
    url = f"{S2_API}{path}"
    for attempt in range(3):
        resp = requests.get(url, params=params, headers=S2_HEADERS, timeout=timeout)
        if resp.status_code == 429 and attempt < 2:
            time.sleep(5)
            continue
        if resp.status_code == 429:
            return None, f"{path} returned 429 rate-limit after retries"
        if resp.status_code >= 500 and attempt < 2:
            time.sleep(3)
            continue
        if 400 <= resp.status_code < 500:
            return None, f"{path} returned HTTP {resp.status_code}"
        resp.raise_for_status()
        return resp.json(), None
    return None, f"{path} returned repeated server errors"


def semantic_scholar_search(query: str, limit: int) -> tuple[list[dict], list[str]]:
    params = {
        "query": query,
        "limit": max(1, min(limit, 20)),
        "fields": "title,year,venue,abstract,citationCount,externalIds,tldr",
    }
    diagnostics: list[str] = []
    # Normal search is often better for narrow queries; bulk remains useful for broad
    # academic exploration and mirrors the SkyDiscover-style fallback.
    data, error = s2_get("/graph/v1/paper/search", params)
    if data and data.get("data"):
        return data.get("data", []), diagnostics
    if error:
        diagnostics.append(error)
    else:
        diagnostics.append("/graph/v1/paper/search returned 0 results")
    data, error = s2_get("/graph/v1/paper/search/bulk", params)
    if data and data.get("data"):
        return data.get("data", []), diagnostics
    if error:
        diagnostics.append(error)
    else:
        diagnostics.append("/graph/v1/paper/search/bulk returned 0 results")
    if not S2_API_KEY:
        diagnostics.append("S2_API_KEY is not set; unauthenticated Semantic Scholar searches may be rate-limited")
    return [], diagnostics


def semantic_scholar_snippets(query: str, limit: int) -> tuple[list[dict], list[str]]:
    data, error = s2_get(
        "/graph/v1/snippet/search",
        {
            "query": query,
            "limit": max(1, min(limit, 20)),
            "fields": "title,externalIds,year,citationCount",
        },
    )
    if data and data.get("data"):
        return data.get("data", []), []
    diagnostics = [error or "/graph/v1/snippet/search returned 0 results"]
    if not S2_API_KEY:
        diagnostics.append("S2_API_KEY is not set; unauthenticated Semantic Scholar searches may be rate-limited")
    return [], diagnostics


def format_results(papers: list[dict], query: str, diagnostics: list[str] | None = None) -> str:
    if not papers:
        suffix = ""
        if diagnostics:
            suffix = "\nDiagnostics:\n" + "\n".join(f"- {item}" for item in diagnostics)
        return f"No papers found for {query!r}.{suffix}"
    lines = [f"# Literature search results for {query!r}"]
    for idx, paper in enumerate(papers, start=1):
        title = paper.get("title") or "(untitled)"
        year = paper.get("year") or "?"
        venue = paper.get("venue") or ""
        cites = paper.get("citationCount", 0)
        tldr = (paper.get("tldr") or {}).get("text") or ""
        abstract = paper.get("abstract") or ""
        summary = tldr or abstract[:500]
        search_link = "https://www.semanticscholar.org/search?" + urlencode({"q": title})
        lines.append(f"\n## {idx}. {title}")
        lines.append(f"Year: {year} | Venue: {venue or 'unknown'} | Citations: {cites}")
        lines.append(search_link)
        if summary:
            lines.append(summary)
    return "\n".join(lines)


def format_snippets(snippets: list[dict], query: str, diagnostics: list[str] | None = None) -> str:
    if not snippets:
        suffix = ""
        if diagnostics:
            suffix = "\nDiagnostics:\n" + "\n".join(f"- {item}" for item in diagnostics)
        return f"No snippets found for {query!r}.{suffix}"
    lines = [f"# Snippet search results for {query!r}"]
    for idx, item in enumerate(snippets, start=1):
        paper = item.get("paper") or {}
        title = paper.get("title") or "(untitled)"
        year = paper.get("year") or "?"
        cites = paper.get("citationCount", 0)
        snippet = item.get("snippet") or {}
        text = snippet.get("text") or ""
        section = snippet.get("section") or ""
        lines.append(f"\n## {idx}. {title}")
        lines.append(f"Year: {year} | Citations: {cites}")
        if section:
            lines.append(f"Section: {section}")
        if text:
            lines.append(truncate(text, 600))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Constrained literature search for background methods and datasets.")
    parser.add_argument("operation", choices=sorted(ALLOWED_OPERATIONS))
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    request = vars(args)
    deny = deny_leaky_query(args.query)
    if deny:
        response = {"error": deny}
        append_tool_event("research_papers", request, response, "denied")
        print(deny, file=sys.stderr)
        return 2
    try:
        if args.operation == "snippet_search":
            snippets, diagnostics = semantic_scholar_snippets(args.query, args.limit)
            if snippets:
                output = truncate(format_snippets(snippets, args.query))
                response = {
                    "operation": args.operation,
                    "count": len(snippets),
                    "diagnostics": diagnostics,
                    "content": output,
                }
                append_tool_event("research_papers", request, response, "ok")
                print(output)
                return 0
        papers, diagnostics = semantic_scholar_search(args.query, args.limit)
        output = truncate(format_results(papers, args.query, diagnostics))
        response = {
            "operation": args.operation,
            "count": len(papers),
            "diagnostics": diagnostics,
            "content": output,
        }
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
