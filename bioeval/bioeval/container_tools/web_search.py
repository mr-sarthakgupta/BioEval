#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
import sys
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from bioeval_tool_common import append_tool_event, blocked_url_reason, deny_leaky_query, host_matches, truncate


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
        resp = requests.get(search_url(args.query), headers={"User-Agent": "BioEval/1.0"}, timeout=20)
        resp.raise_for_status()
        parser_obj = LinkParser()
        parser_obj.feed(resp.text)
        rows = []
        seen = set()
        allowed = {d.lower() for d in args.allowed_domain}
        blocked = {d.lower() for d in args.blocked_domain}
        for raw_url, title in parser_obj.links:
            url = decode_url(raw_url)
            if not url or url in seen or "duckduckgo.com" in url:
                continue
            if blocked_url_reason(url):
                continue
            if allowed and not host_matches(url, allowed):
                continue
            if blocked and host_matches(url, blocked):
                continue
            seen.add(url)
            rows.append({"title": re.sub(r"\s+", " ", title), "url": url})
            if len(rows) >= max(1, min(args.limit, 20)):
                break
        text = "\n".join(f"{idx}. {row['title']}\n   {row['url']}" for idx, row in enumerate(rows, start=1))
        output = truncate(text or "No search results.")
        response = {"results": rows, "content": output}
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
