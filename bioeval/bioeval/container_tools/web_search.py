#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from bioeval_tool_common import append_tool_event, blocked_url_reason, deny_leaky_query, host_matches, truncate

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
S2_API_KEY = os.getenv("S2_API_KEY")
S2_HEADERS = {"x-api-key": S2_API_KEY} if S2_API_KEY else {}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self.href: str | None = None
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attrs_map = {k: v or "" for k, v in attrs}
        href = attrs_map.get("href")
        if href:
            self.href = href
            self.text = []

    def handle_data(self, data: str) -> None:
        if self.href:
            self.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self.href:
            title = " ".join("".join(self.text).split())
            if title:
                self.links.append((self.href, title))
            self.href = None


def decode_url(raw: str) -> str | None:
    if raw.startswith("http://") or raw.startswith("https://"):
        return html.unescape(raw)
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("/"):
        parsed = urlparse("https://duckduckgo.com" + raw)
        if parsed.path in {"/l", "/l/"}:
            uddg = parse_qs(parsed.query).get("uddg", [])
            if uddg:
                return html.unescape(uddg[0])
    return None


def search_url(query: str) -> str:
    parsed = urlparse("https://html.duckduckgo.com/html/")
    return urlunparse(parsed._replace(query=urlencode({"q": query})))


def s2_fallback_search(query: str, limit: int) -> tuple[list[dict[str, str]], list[str]]:
    diagnostics: list[str] = []
    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search/bulk",
            params={
                "query": query,
                "limit": max(1, min(limit, 20)),
                "fields": "title,externalIds,year,citationCount,venue,publicationDate",
            },
            headers=S2_HEADERS,
            timeout=15,
        )
        if resp.status_code == 429:
            time.sleep(5)
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search/bulk",
                params={
                    "query": query,
                    "limit": max(1, min(limit, 20)),
                    "fields": "title,externalIds,year,citationCount,venue,publicationDate",
                },
                headers=S2_HEADERS,
                timeout=15,
            )
        if resp.status_code != 200:
            diagnostics.append(f"Semantic Scholar fallback returned HTTP {resp.status_code}")
            if not S2_API_KEY:
                diagnostics.append("S2_API_KEY is not set; fallback searches may be rate-limited")
            return [], diagnostics
        rows = []
        for paper in resp.json().get("data", []):
            title = paper.get("title") or ""
            ext = paper.get("externalIds") or {}
            url = ""
            if ext.get("DOI"):
                url = f"https://doi.org/{ext['DOI']}"
            elif ext.get("ArXiv"):
                url = f"https://arxiv.org/abs/{ext['ArXiv']}"
            elif paper.get("paperId"):
                url = f"https://www.semanticscholar.org/paper/{paper['paperId']}"
            if not title or not url:
                continue
            venue = paper.get("venue") or ""
            year = paper.get("year") or ""
            suffix = f" ({venue}, {year})" if venue and year else f" ({year})" if year else ""
            rows.append({"title": title + suffix, "url": url})
        if not rows:
            diagnostics.append("Semantic Scholar fallback returned 0 usable results")
            if not S2_API_KEY:
                diagnostics.append("S2_API_KEY is not set; fallback searches may be rate-limited")
        return rows, diagnostics
    except Exception as exc:
        diagnostics.append(f"Semantic Scholar fallback failed: {exc}")
        return [], diagnostics


def main() -> int:
    parser = argparse.ArgumentParser(description="Search the web with blind-setup constraints.")
    parser.add_argument("query")
    parser.add_argument("--allowed-domain", action="append", default=[])
    parser.add_argument("--blocked-domain", action="append", default=[])
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()
    request = vars(args)
    deny = deny_leaky_query(args.query)
    if deny:
        response = {"error": deny}
        append_tool_event("web_search", request, response, "denied")
        print(deny, file=sys.stderr)
        return 2
    try:
        rows = []
        diagnostics: list[str] = []
        duckduckgo_error = None
        for attempt in range(2):
            try:
                resp = requests.get(search_url(args.query), headers={"User-Agent": USER_AGENT}, timeout=20)
                resp.raise_for_status()
            except Exception as exc:  # noqa: BLE001 - report and try fallback
                duckduckgo_error = str(exc)
                break
            parser_obj = LinkParser()
            parser_obj.feed(resp.text)
            for raw_url, title in parser_obj.links:
                url = decode_url(raw_url)
                if not url or "duckduckgo.com" in url:
                    continue
                rows.append({"title": re.sub(r"\s+", " ", title), "url": url})
            if rows or attempt:
                break
            time.sleep(1)
        duckduckgo_count = len(rows)
        used_s2_fallback = False
        if not rows:
            if duckduckgo_error:
                diagnostics.append(f"DuckDuckGo search failed: {duckduckgo_error}")
            else:
                diagnostics.append("DuckDuckGo returned 0 parsable external results")
            rows, s2_diagnostics = s2_fallback_search(args.query, args.limit)
            diagnostics.extend(s2_diagnostics)
            used_s2_fallback = bool(rows)
        seen = set()
        allowed = {d.lower() for d in args.allowed_domain}
        blocked = {d.lower() for d in args.blocked_domain}
        filtered = []
        blocked_by_guard = 0
        blocked_by_request = 0
        blocked_by_allowed = 0
        used_s2_fallback = used_s2_fallback or (
            bool(rows)
            and any("semanticscholar.org" in row["url"] or "doi.org" in row["url"] or "arxiv.org" in row["url"] for row in rows)
        )
        for row in rows:
            url = row["url"]
            if url in seen:
                continue
            if blocked_url_reason(url):
                blocked_by_guard += 1
                continue
            if allowed and not host_matches(url, allowed):
                blocked_by_allowed += 1
                continue
            if blocked and host_matches(url, blocked):
                blocked_by_request += 1
                continue
            seen.add(url)
            filtered.append(row)
            if len(filtered) >= max(1, min(args.limit, 20)):
                break
        if rows and not filtered:
            diagnostics.append(
                "Search returned candidate results, but none survived filtering "
                f"(blind-setup guard blocked {blocked_by_guard}, allowed-domain filter blocked "
                f"{blocked_by_allowed}, request blocked-domain filter blocked {blocked_by_request})."
            )
        elif blocked_by_guard or blocked_by_allowed or blocked_by_request:
            diagnostics.append(
                f"Filtered candidates: blind-setup guard={blocked_by_guard}, "
                f"allowed-domain={blocked_by_allowed}, blocked-domain={blocked_by_request}."
            )
        source_note = "\n(via Semantic Scholar academic fallback)" if used_s2_fallback else ""
        text = "\n".join(f"{idx}. {row['title']}\n   {row['url']}" for idx, row in enumerate(filtered, start=1))
        if text and source_note:
            text += source_note
        if not text and diagnostics:
            text = "No search results.\nDiagnostics:\n" + "\n".join(f"- {item}" for item in diagnostics)
        output = truncate(text or "No search results.")
        response = {
            "results": filtered,
            "counts": {
                "duckduckgo_candidates": duckduckgo_count,
                "total_candidates": len(rows),
                "returned": len(filtered),
                "blocked_by_guard": blocked_by_guard,
                "blocked_by_allowed_domain": blocked_by_allowed,
                "blocked_by_requested_domain": blocked_by_request,
            },
            "diagnostics": diagnostics,
            "content": output,
        }
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
