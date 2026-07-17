from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


WORKSPACE = Path(os.getenv("BIOEVAL_WORKSPACE", "/workspace")).resolve()
REFERENCE_DIR = WORKSPACE / "reference"
TOOL_LOG = Path(os.getenv("BIOEVAL_TOOL_LOG", "/submit/tool_calls.jsonl"))
MAX_OUTPUT_CHARS = int(os.getenv("BIOEVAL_TOOL_MAX_OUTPUT_CHARS", "20000"))

DENIED_QUERY_RE = re.compile(
    r"\b(paper|manuscript|article|authors'? code|source code|github|repository|"
    r"\brepo\b|solution|answer key|ground truth|expected (?:result|conclusion)|doi)\b",
    re.IGNORECASE,
)
def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_tool_event(tool: str, request: dict[str, Any], response: dict[str, Any], status: str) -> None:
    TOOL_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "event": "tool_call",
        "timestamp": utc_now(),
        "run_id": os.getenv("BIOEVAL_RUN_ID"),
        "tool": tool,
        "status": status,
        "request": request,
        "response": response,
    }
    with TOOL_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def truncate(text: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    omitted = len(text) - max_chars
    return f"{text[:half]}\n\n... ({omitted} chars truncated) ...\n\n{text[-half:]}"


def workspace_path(path: str, *, must_exist: bool = True) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = WORKSPACE / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(WORKSPACE)
    except ValueError as exc:
        raise ValueError("path must stay inside /workspace") from exc
    if must_exist and not resolved.exists():
        raise FileNotFoundError(str(path))
    return resolved


def relative_workspace_path(path: Path) -> str:
    return str(path.resolve().relative_to(WORKSPACE))


def deny_leaky_query(text: str) -> str | None:
    if DENIED_QUERY_RE.search(text):
        return (
            "This request cannot be fulfilled. Please ask for general background, "
            "methods, or specific data instead."
        )
    return None


def host_matches(url: str, domains: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().lstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def blocked_url_reason(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "URL must be http(s)."
    extra = os.getenv("BIOEVAL_BLOCKED_WEB_DOMAINS", "")
    blocked = {domain.strip().lower() for domain in extra.split(",") if domain.strip()}
    if blocked and host_matches(url, blocked):
        return "This URL cannot be fetched."
    return None
