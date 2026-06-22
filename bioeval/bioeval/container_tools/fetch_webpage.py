#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from html.parser import HTMLParser

import requests

from bioeval_tool_common import (
    REFERENCE_DIR,
    append_tool_event,
    blocked_url_reason,
    relative_workspace_path,
    truncate,
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class TextExtractor(HTMLParser):
    skip_tags = {"script", "style", "noscript", "head", "nav", "footer", "header", "aside", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.skip_depth or tag.lower() in self.skip_tags:
            self.skip_depth += 1
        elif tag.lower() in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.skip_depth:
            self.skip_depth -= 1
        elif tag.lower() in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        text = html.unescape("".join(self.parts))
        text = re.sub(r"[ \t]+", " ", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()


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
    reason = blocked_url_reason(args.url)
    if reason:
        response = {"error": reason}
        append_tool_event("fetch_webpage", request, response, "denied")
        print(f"Denied: {reason}", file=sys.stderr)
        return 2
    try:
        resp = requests.get(args.url, headers={"User-Agent": USER_AGENT}, timeout=30, allow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        if "pdf" in content_type or "octet-stream" in content_type:
            raise ValueError("binary/PDF content is not fetchable through this text tool")
        if "html" in content_type or not content_type:
            extractor = TextExtractor()
            extractor.feed(resp.text)
            text = extractor.text()
        else:
            text = resp.text
        text = truncate(text, args.max_chars)
        REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
        path = REFERENCE_DIR / f"web_{slug(args.url)}.txt"
        path.write_text(
            f"# Fetched page: {args.url}\n# Content-Type: {content_type}\n\n{text}\n",
            encoding="utf-8",
            errors="replace",
        )
        rel = relative_workspace_path(path)
        response = {"saved_path": rel, "url": args.url, "chars": len(text)}
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
