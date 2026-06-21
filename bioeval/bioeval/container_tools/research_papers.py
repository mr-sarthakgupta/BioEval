#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from urllib.parse import urlencode

import requests

from bioeval_tool_common import append_tool_event, deny_leaky_query, truncate


ALLOWED_OPERATIONS = {"search", "snippet_search"}


def semantic_scholar_search(query: str, limit: int) -> list[dict]:
    resp = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": query,
            "limit": max(1, min(limit, 20)),
            "fields": "title,year,venue,abstract,citationCount,externalIds,tldr",
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def format_results(papers: list[dict], query: str) -> str:
    if not papers:
        return f"No papers found for {query!r}."
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
        papers = semantic_scholar_search(args.query, args.limit)
        output = truncate(format_results(papers, args.query))
        response = {"operation": args.operation, "count": len(papers), "content": output}
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
