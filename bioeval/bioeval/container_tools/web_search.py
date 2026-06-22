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


def s2_fallback_search(query: str, limit: int) -> list[dict[str, str]]:
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
            return []
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
        return rows
    except Exception:
        return []


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
        for attempt in range(2):
            resp = requests.get(search_url(args.query), headers={"User-Agent": USER_AGENT}, timeout=20)
            resp.raise_for_status()
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
        if not rows:
            rows = s2_fallback_search(args.query, args.limit)
        seen = set()
        allowed = {d.lower() for d in args.allowed_domain}
        blocked = {d.lower() for d in args.blocked_domain}
        filtered = []
        used_s2_fallback = bool(rows) and any("semanticscholar.org" in row["url"] or "doi.org" in row["url"] or "arxiv.org" in row["url"] for row in rows)
        for row in rows:
            url = row["url"]
            if url in seen:
                continue
            if blocked_url_reason(url):
                continue
            if allowed and not host_matches(url, allowed):
                continue
            if blocked and host_matches(url, blocked):
                continue
            seen.add(url)
            filtered.append(row)
            if len(filtered) >= max(1, min(args.limit, 20)):
                break
        source_note = "\n(via Semantic Scholar academic fallback)" if used_s2_fallback else ""
        text = "\n".join(f"{idx}. {row['title']}\n   {row['url']}" for idx, row in enumerate(filtered, start=1))
        if text and source_note:
            text += source_note
        output = truncate(text or "No search results.")
        response = {"results": filtered, "content": output}
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
