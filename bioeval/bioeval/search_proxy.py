from __future__ import annotations

import html
import hashlib
import json
import logging
import os
import re
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import requests

from bioeval.bedrock_cost import record_bedrock_usage
from bioeval.bedrock_client import (
    create_bedrock_client,
    extract_text_from_response,
    is_bedrock_api_base,
    prompt_cache_point,
)
from bioeval.providers import _safe_urlopen, _validate_public_url

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
FETCH_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_FETCH_BYTES = int(os.getenv("BIOEVAL_FETCH_WEBPAGE_MAX_BYTES", "10000000"))
OPENALEX_API = "https://api.openalex.org"
OPENALEX_API_KEY_FILE = os.getenv("OPENALEX_API_KEY_FILE", "/home/mrsar/openalex_key.txt")
OPENALEX_WORK_SELECT = (
    "id,doi,title,display_name,publication_year,publication_date,primary_location,"
    "cited_by_count,ids,abstract_inverted_index"
)
OPENALEX_GRAPH_SELECT = "id"
OPENALEX_GRAPH_BATCH_SIZE = 20
OPENALEX_GRAPH_CACHE_TTL = int(os.getenv("BIOEVAL_OPENALEX_GRAPH_CACHE_TTL", "21600"))
OPENALEX_GRAPH_ERROR_TTL = int(os.getenv("BIOEVAL_OPENALEX_GRAPH_ERROR_TTL", "300"))
OPENALEX_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
OPENALEX_ID_RE = re.compile(r"(?:https?://openalex\.org/)?(W\d+)", re.IGNORECASE)
OPENALEX_GRAPH_CACHE: dict[str, tuple[float, frozenset[str], bool]] = {}
OPENALEX_GRAPH_LOCK = threading.Lock()
OPENALEX_DOI_ID_CACHE: dict[str, str | None] = {}
LOGGER = logging.getLogger(__name__)

DENIED_QUERY_RE = re.compile(
    r"\b(paper|manuscript|article|authors'? code|source code|github|repository|"
    r"\brepo\b|solution|answer key|ground truth|expected (?:result|conclusion)|doi)\b",
    re.IGNORECASE,
)
DEFAULT_GUARD_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_GUARD_API_BASE = "bedrock:us-east-1"
TRAFFIC_GUARD_SYSTEM_PROMPT = """You are the traffic guard for BioEval, a blind scientific discovery benchmark.

Your only job is to decide whether one search query, search result, paper result, snippet,
or fetched page may be shown to the under-evaluation research agent.

The research agent must NOT see the held-out work used for evaluation, and must NOT see
derivative works that reveal that held-out work. Block any item that is, points to, quotes,
summarizes, identifies, or retrieves:
- the original held-out paper, manuscript, preprint, DOI/PMID/PMCID landing page, journal page,
  abstract page, full text, PDF, supplementary information, source-data table, public data deposit,
  repository, author code, trained model, README, metadata, or record page;
- a derivative of the held-out work, including preprint versions, conference abstracts, dataset
  records for that paper, repository mirrors/forks, author/project pages about that paper, press
  releases, news/blog/social posts, OpenAlex/PubMed/Europe PMC records, citation pages,
  review snippets, or any search result that reveals the title, authors, identifiers, central
  claims, or paper-specific datasets of the held-out work;
- a source that would let the research agent directly navigate to the held-out work or its
  derivative artifacts.

Do NOT block legitimate predecessor or background work. Allow independent earlier papers,
methods, reviews, datasets, and resources that predate or are conceptually upstream of the
held-out work, even if they discuss the same scientific field, organisms, assays, or methods.
For example, classic mechanism papers, general review articles, public databases, and earlier
independent datasets are allowed unless they identify or summarize the held-out work.

When a candidate includes `external_source_cutoff`, BLOCK independent sources published
after that instant. For target-relevant papers, datasets, news, reviews, or mutable pages,
BLOCK when the publication/release date cannot be established as on or before the cutoff.
Target-lineage material remains blocked regardless of whether it predates the cutoff.

Decision rule:
- BLOCK if the item is the held-out work, a derivative/source/record of it, or would expose
  title/authors/DOI/PMID/repository/data-deposit/specific conclusions of it.
- ALLOW if it is general background or predecessor work and does not reveal the held-out work.
- If uncertain whether something is predecessor/background versus a derivative/source of the
  held-out work, BLOCK.

Some candidates include a `text_resource` handle. When available, you may use the
guard_text_search and guard_read_text tools to inspect the retrieved metadata, snippet,
or page text before deciding. Search for held-out identifiers, title fragments,
author names, DOI/PMID/PMCID, source-data/deposit terms, repository/code terms,
and distinctive conclusion language as needed. Do not request or reveal the full
resource unless necessary; inspect focused ranges.

Return ONLY a JSON object:
{"decision":"allow"|"block","reason":"brief precise reason"}
"""

TRAFFIC_GUARD_TYPE_INSTRUCTIONS = {
    "research_query": (
        "Review a literature-search query before sending it to an academic search API. "
        "BLOCK queries that search for the held-out paper directly, including exact or "
        "near-exact title strings, DOI/PMID/PMCID, author-title combinations, repository "
        "or dataset-record names, quoted distinctive target claims, or searches intended "
        "to locate the paper/preprint/source data. ALLOW broad background, predecessor, "
        "methods, review, organism/assay, or field-level searches that do not identify "
        "or summarize the held-out work."
    ),
    "research_paper_result": (
        "Review one paper metadata result before showing it to the research agent. BLOCK "
        "if the title, abstract, TLDR, venue metadata, or external identifiers indicate "
        "the held-out paper, a preprint/version of it, a citation/record page for it, "
        "a dataset/source-data record for it, or a derivative that reveals its title, "
        "authors, identifiers, central claims, or paper-specific datasets. ALLOW earlier "
        "independent papers, classic mechanisms, general reviews, and predecessor datasets "
        "that are merely in the same field. If candidate.text_resource is present, use the "
        "available text tools to search/read the retrieved metadata before deciding."
    ),
    "research_snippet_result": (
        "Review one passage/snippet result before showing it to the research agent. BLOCK "
        "if the snippet or associated paper metadata reveals the held-out paper title, "
        "authors, identifiers, abstract-like summary, central conclusion, figure/source-data "
        "content, or a citation/data record for the held-out work. BLOCK near-title snippets "
        "even if the paper result is otherwise sparse. ALLOW snippets about independent "
        "background biology, predecessor methods, or related mechanisms that do not identify "
        "or summarize the held-out work. If candidate.text_resource is present, use the "
        "available text tools to inspect the retrieved snippet and metadata before deciding."
    ),
    "web_query": (
        "Review a general web-search query before sending it to the search provider. BLOCK "
        "queries that are likely to retrieve the held-out paper or its derivatives because "
        "they include exact/near-exact titles, DOI/PMID/PMCID, author-title combinations, "
        "repository/deposit names, quoted target conclusions, or source-data phrases. ALLOW "
        "broad background searches for concepts, assays, organisms, methods, reviews, or "
        "independent public resources that do not identify the held-out work."
    ),
    "web_search_result": (
        "Review one web-search result before showing it to the research agent. BLOCK if "
        "the title or URL points to the held-out paper, preprint, journal landing page, "
        "PubMed/PMC/OpenAlex/Europe PMC/citation page, public data deposit, source "
        "data, author repository, press/news/social derivative, or any page revealing the "
        "held-out title, authors, identifiers, or conclusions. ALLOW independent background "
        "resources, database documentation, methods pages, and predecessor work. At this "
        "stage you usually have only title and URL; if metadata is inconclusive, ALLOW so "
        "fetch_url and fetched_page_content can inspect the URL and page text."
    ),
    "fetch_url": (
        "Review a URL before fetching it. BLOCK if the URL appears to be the held-out "
        "paper/preprint, DOI resolver, PMID/PMCID page, journal page, PDF/supplement/source "
        "data, public data deposit/record, author repository/code archive, citation page, "
        "or derivative page about the held-out work. BLOCK suspicious redirects or URLs "
        "containing held-out identifiers. ALLOW URLs for independent background resources, "
        "general methods, reviews, and predecessor datasets."
    ),
    "fetched_page_content": (
        "Review fetched page text before showing it to the research agent. BLOCK if the "
        "page content identifies, quotes, summarizes, or links to the held-out work; includes "
        "its title, authors, DOI/PMID/PMCID, abstract, key conclusions, source-data/deposit "
        "details, repository/code/model details, figure captions, or citation/record metadata. "
        "ALLOW content that is general background, predecessor literature, methods, or "
        "independent datasets and does not reveal the held-out work. You MUST use "
        "candidate.text_resource with the available text tools to search/read relevant parts "
        "of the fetched page before deciding; do not decide from URL or metadata alone."
    ),
}

_GUARD_DECISION_CACHE: dict[str, dict[str, str]] = {}
_GUARD_TEXT_RESOURCES: dict[str, str] = {}
PUBLIC_GUARD_DENIAL = "No results found."


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


class TextExtractor(HTMLParser):
    skip_tags = {"script", "style", "noscript", "head", "nav", "footer", "header", "aside", "svg"}
    void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.void_tags:
            if not self.skip_depth and tag == "br":
                self.parts.append("\n")
            return
        if self.skip_depth or tag in self.skip_tags:
            self.skip_depth += 1
        elif tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.skip_depth and tag.lower() == "br":
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


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def marker_variants(identifiers: list[str]) -> list[str]:
    variants: list[str] = []
    for raw in identifiers:
        raw = (raw or "").strip()
        if not raw:
            continue
        candidates = {raw}
        if raw.startswith("10."):
            candidates.add(f"doi.org/{raw}")
            candidates.add(raw.replace("/", " "))
            candidates.add(raw.replace("/", "-"))
        for candidate in candidates:
            normalized = normalize_text(candidate)
            compact = re.sub(r"\s+", "", normalized)
            # Search filtering can use shorter markers than content scanning, but
            # keep them specific enough to avoid suppressing generic literature.
            if len(normalized) >= 6 or (len(normalized) >= 5 and candidate.isupper()):
                variants.append(normalized)
            if len(compact) >= 10:
                variants.append(compact)
    return list(dict.fromkeys(variants))


def contains_hidden_identifier(text: str, identifiers: list[str]) -> bool:
    if not text:
        return False
    normalized = normalize_text(text)
    compact = re.sub(r"\s+", "", normalized)
    for marker in marker_variants(identifiers):
        if " " in marker:
            if marker in normalized:
                return True
        elif marker in compact or re.search(rf"\b{re.escape(marker)}\b", normalized):
            return True
    return False


def make_guard_text_resource(text: str, description: str) -> dict:
    """Register retrievable guard-only text without embedding it in the prompt."""
    text = text or ""
    digest = hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:16]
    resource_id = f"guard_text_{digest}"
    _GUARD_TEXT_RESOURCES[resource_id] = text
    return {
        "id": resource_id,
        "description": description,
        "char_count": len(text),
        "tools": ["guard_text_search", "guard_read_text"],
    }


def guard_text_search(resource_id: str, query: str, max_matches: int = 8, context_chars: int = 260) -> dict:
    text = _GUARD_TEXT_RESOURCES.get(resource_id)
    if text is None:
        return {"error": f"unknown text_resource id: {resource_id}"}
    query = query or ""
    if not query:
        return {"matches": []}
    max_matches = max(1, min(max_matches, 20))
    context_chars = max(40, min(context_chars, 1000))
    matches = []
    for match in re.finditer(re.escape(query), text, flags=re.IGNORECASE):
        start = max(0, match.start() - context_chars)
        end = min(len(text), match.end() + context_chars)
        matches.append(
            {
                "start": match.start(),
                "end": match.end(),
                "excerpt": ("..." if start > 0 else "")
                + re.sub(r"\s+", " ", text[start:end]).strip()
                + ("..." if end < len(text) else ""),
            }
        )
        if len(matches) >= max_matches:
            break
    return {"resource_id": resource_id, "query": query, "matches": matches}


def guard_read_text(resource_id: str, start: int = 0, length: int = 1200) -> dict:
    text = _GUARD_TEXT_RESOURCES.get(resource_id)
    if text is None:
        return {"error": f"unknown text_resource id: {resource_id}"}
    start = max(0, min(start, len(text)))
    length = max(1, min(length, 4000))
    end = min(len(text), start + length)
    return {
        "resource_id": resource_id,
        "start": start,
        "end": end,
        "char_count": len(text),
        "text": text[start:end],
    }


def _extract_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _guard_enabled() -> bool:
    return os.getenv("BIOEVAL_TRAFFIC_GUARD_ENABLED", "1").lower() not in {
        "0",
        "false",
        "off",
        "none",
    }


def _guard_fail_closed() -> bool:
    return os.getenv("BIOEVAL_TRAFFIC_GUARD_FAIL_CLOSED", "1").lower() not in {
        "0",
        "false",
        "off",
        "none",
    }


def _guard_input(
    *,
    kind: str,
    candidate: dict,
    identifiers: list[str],
) -> str:
    return json.dumps(
        {
            "held_out_identifiers": [identifier for identifier in identifiers if identifier],
            "item_type": kind,
            "candidate": candidate,
            "instruction": TRAFFIC_GUARD_TYPE_INSTRUCTIONS.get(
                kind,
                (
                    "Decide whether this candidate can be shown to the research agent. "
                    "Block the held-out work and derivatives/sources/records of it. "
                    "Allow predecessor/background work that does not identify or summarize the held-out work."
                ),
            ),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _guard_tool_config() -> dict:
    string = {"type": "string"}
    integer = {"type": "integer"}
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "guard_text_search",
                    "description": (
                        "Search a guard-only text resource for a string and return matching "
                        "excerpts with character offsets."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "resource_id": string,
                                "query": string,
                                "max_matches": integer,
                                "context_chars": integer,
                            },
                            "required": ["resource_id", "query"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "guard_read_text",
                    "description": (
                        "Read a character range from a guard-only text resource. Use offsets "
                        "from guard_text_search or read the beginning for orientation."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "resource_id": string,
                                "start": integer,
                                "length": integer,
                            },
                            "required": ["resource_id"],
                        }
                    },
                }
            },
        ]
    }


def _candidate_has_text_resource(candidate: dict) -> bool:
    resource = candidate.get("text_resource")
    return isinstance(resource, dict) and bool(resource.get("id"))


def _guard_requires_text_inspection(kind: str, candidate: dict) -> bool:
    return kind == "fetched_page_content" and _candidate_has_text_resource(candidate)


def _extract_message_text_and_tools(message: dict) -> tuple[str, list[dict]]:
    text_parts = []
    tool_uses = []
    for item in message.get("content", []) or []:
        if "text" in item:
            text_parts.append(item.get("text") or "")
        if "toolUse" in item:
            tool_uses.append(item["toolUse"])
    return "\n".join(part for part in text_parts if part).strip(), tool_uses


def _execute_guard_tool(name: str, payload: dict) -> dict:
    if name == "guard_text_search":
        return guard_text_search(
            resource_id=str(payload.get("resource_id", "")),
            query=str(payload.get("query", "")),
            max_matches=int(payload.get("max_matches") or 8),
            context_chars=int(payload.get("context_chars") or 260),
        )
    if name == "guard_read_text":
        return guard_read_text(
            resource_id=str(payload.get("resource_id", "")),
            start=int(payload.get("start") or 0),
            length=int(payload.get("length") or 1200),
        )
    return {"error": f"unknown guard tool: {name}"}


def traffic_guard_decision(
    *,
    kind: str,
    candidate: dict,
    identifiers: list[str],
    model: str | None = None,
    api_base: str | None = None,
) -> dict[str, str]:
    """Return a guard-agent allow/block decision for non-deterministically-blocked traffic."""
    if not _guard_enabled():
        return {"decision": "allow", "reason": "traffic guard disabled"}

    payload = _guard_input(kind=kind, candidate=candidate, identifiers=identifiers)
    cache_key = f"{kind}:{payload}"
    if cache_key in _GUARD_DECISION_CACHE:
        return _GUARD_DECISION_CACHE[cache_key]

    model = (
        model
        or os.getenv("BIOEVAL_TRAFFIC_GUARD_MODEL")
        or os.getenv("EXPERIMENT_AGENT_MODEL")
        or DEFAULT_GUARD_MODEL
    )
    api_base = (
        api_base
        or os.getenv("BIOEVAL_TRAFFIC_GUARD_API_BASE")
        or os.getenv("EXPERIMENT_AGENT_API_BASE")
        or DEFAULT_GUARD_API_BASE
    )

    if not is_bedrock_api_base(api_base):
        if _guard_fail_closed():
            return {
                "decision": "block",
                "reason": "traffic guard requires Bedrock and is configured fail-closed",
            }
        return {"decision": "allow", "reason": "traffic guard unavailable"}

    try:
        system_blocks = [{"text": TRAFFIC_GUARD_SYSTEM_PROMPT}]
        cache_point = prompt_cache_point()
        if cache_point:
            system_blocks.append(cache_point)
        client = create_bedrock_client(api_base)
        messages = [{"role": "user", "content": [{"text": payload}]}]
        obj = None
        max_rounds = int(os.getenv("BIOEVAL_TRAFFIC_GUARD_TOOL_ROUNDS", "4"))
        used_text_tool = False
        for _ in range(max(1, max_rounds)):
            kwargs = {
                "modelId": model.removeprefix("bedrock/"),
                "system": system_blocks,
                "messages": messages,
                "inferenceConfig": {
                    "maxTokens": int(os.getenv("BIOEVAL_TRAFFIC_GUARD_MAX_TOKENS", "512")),
                    "temperature": 0,
                },
            }
            if _candidate_has_text_resource(candidate):
                kwargs["toolConfig"] = _guard_tool_config()
            response = client.converse(**kwargs)
            if response.get("usage"):
                record_bedrock_usage(response["usage"], component="traffic-guard", model=model)
            message = response.get("output", {}).get("message", {})
            text, tool_uses = _extract_message_text_and_tools(message)
            messages.append({"role": "assistant", "content": message.get("content", [])})
            if not tool_uses:
                if _guard_requires_text_inspection(kind, candidate) and not used_text_tool:
                    messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": (
                                        "This candidate includes fetched page text. Use "
                                        "guard_text_search or guard_read_text to inspect the "
                                        "text_resource before returning allow/block."
                                    )
                                }
                            ],
                        }
                    )
                    continue
                obj = _extract_json_object(text or extract_text_from_response(response))
                break
            tool_results = []
            for tool_use in tool_uses:
                result = _execute_guard_tool(tool_use.get("name", ""), tool_use.get("input") or {})
                if tool_use.get("name") in {"guard_text_search", "guard_read_text"}:
                    used_text_tool = True
                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_use["toolUseId"],
                            "status": "error" if "error" in result else "success",
                            "content": [{"text": json.dumps(result, ensure_ascii=False)}],
                        }
                    }
                )
            messages.append({"role": "user", "content": tool_results})
    except Exception as exc:  # noqa: BLE001 - keep traffic safe if the guard breaks
        decision = (
            {
                "decision": "block",
                "reason": f"traffic guard failed closed: {exc}",
            }
            if _guard_fail_closed()
            else {"decision": "allow", "reason": f"traffic guard unavailable: {exc}"}
        )
        _GUARD_DECISION_CACHE[cache_key] = decision
        return decision

    if not isinstance(obj, dict) or obj.get("decision") not in {"allow", "block"}:
        decision = (
            {"decision": "block", "reason": "traffic guard returned an invalid decision"}
            if _guard_fail_closed()
            else {"decision": "allow", "reason": "traffic guard returned an invalid decision"}
        )
        _GUARD_DECISION_CACHE[cache_key] = decision
        return decision

    decision = {
        "decision": str(obj["decision"]),
        "reason": str(obj.get("reason") or "no reason provided")[:500],
    }
    _GUARD_DECISION_CACHE[cache_key] = decision
    return decision


def traffic_guard_blocks(
    *,
    kind: str,
    candidate: dict,
    identifiers: list[str],
    model: str | None = None,
    api_base: str | None = None,
) -> str | None:
    decision = traffic_guard_decision(
        kind=kind,
        candidate=candidate,
        identifiers=identifiers,
        model=model,
        api_base=api_base,
    )
    if decision["decision"] == "block":
        return decision["reason"]
    return None


def deny_leaky_query(text: str, identifiers: list[str]) -> str | None:
    if contains_hidden_identifier(text, identifiers):
        return PUBLIC_GUARD_DENIAL
    if DENIED_QUERY_RE.search(text):
        return (
            "This request cannot be fulfilled. Please ask for general background, "
            "methods, or specific data instead."
        )
    return None


def host_matches(url: str, domains: set[str]) -> bool:
    host = (urlparse(url).hostname or "").lower().lstrip(".")
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def blocked_url_reason(url: str, identifiers: list[str]) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "URL must be http(s)."
    if contains_hidden_identifier(url, identifiers):
        return PUBLIC_GUARD_DENIAL
    if openalex_graph_blocks(url, identifiers):
        return PUBLIC_GUARD_DENIAL
    extra = os.getenv("BIOEVAL_BLOCKED_WEB_DOMAINS", "")
    blocked = {domain.strip().lower() for domain in extra.split(",") if domain.strip()}
    if blocked and host_matches(url, blocked):
        return "This URL cannot be fetched."
    return None


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


def duckduckgo_search_url(query: str) -> str:
    parsed = urlparse("https://html.duckduckgo.com/html/")
    return urlunparse(parsed._replace(query=urlencode({"q": query})))


def pmc_eutils_url(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc not in {"pmc.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov"}:
        return None
    match = re.search(r"/(?:pmc/)?articles/(PMC\d+)/?", parsed.path, flags=re.IGNORECASE)
    if not match:
        return None
    pmc_numeric_id = match.group(1)[3:]
    return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?" + urlencode(
        {"db": "pmc", "id": pmc_numeric_id, "retmode": "xml"}
    )


def looks_like_bot_challenge(text: str) -> bool:
    sample = (text or "")[:10000].lower()
    return any(
        marker in sample
        for marker in (
            "checking your browser",
            "just a moment",
            "enable javascript and cookies",
            "verify you are human",
            "cloudflare",
        )
    )


def xml_local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_text(element: ET.Element) -> str:
    return re.sub(r"\s+", " ", " ".join(element.itertext())).strip()


def find_first(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if xml_local_name(child.tag) == name:
            return child
    return None


def extract_nlm_xml_text(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""

    parts: list[str] = []
    title = find_first(root, "article-title")
    if title is not None:
        title_text = element_text(title)
        if title_text:
            parts.append(title_text)

    abstract = find_first(root, "abstract")
    if abstract is not None:
        abstract_parts = [element_text(p) for p in abstract.iter() if xml_local_name(p.tag) == "p"]
        abstract_text = "\n".join(part for part in abstract_parts if part) or element_text(abstract)
        if abstract_text:
            parts.extend(["Abstract", abstract_text])

    body = find_first(root, "body")
    if body is not None:
        for element in body.iter():
            tag = xml_local_name(element.tag)
            if tag == "title":
                text = element_text(element)
                if text:
                    parts.append(text)
            elif tag == "p":
                text = element_text(element)
                if text:
                    parts.append(text)

    return "\n\n".join(parts).strip()


def openalex_web_search_url(title: str) -> str:
    return "https://openalex.org/works?" + urlencode({"filter": f"title.search:{title}"})


def openalex_api_key() -> str | None:
    key = os.getenv("OPENALEX_API_KEY")
    if key:
        return key.strip()
    try:
        with open(OPENALEX_API_KEY_FILE, encoding="utf-8") as key_file:
            return key_file.read().strip() or None
    except OSError:
        return None


def openalex_get(path: str, params: dict, *, timeout: int = 20) -> tuple[dict | None, str | None]:
    api_key = openalex_api_key()
    if not api_key:
        return None, "OPENALEX_API_KEY is not set and no OpenAlex key file is readable"
    url = f"{OPENALEX_API}{path}"
    request_params = {**params, "api_key": api_key}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    for attempt in range(3):
        resp = requests.get(url, params=request_params, headers=headers, timeout=timeout)
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


def normalize_openalex_id(value: str | None) -> str | None:
    match = OPENALEX_ID_RE.search(value or "")
    return match.group(1).upper() if match else None


def hidden_work_doi(identifiers: list[str]) -> str | None:
    for identifier in identifiers:
        match = OPENALEX_DOI_RE.search(identifier or "")
        if match:
            return match.group(0).rstrip(".,;)]}").lower()
    return None


def _openalex_target_id(doi: str) -> tuple[str | None, str | None]:
    data, error = openalex_get(
        "/works",
        {
            "filter": f"doi:{doi}",
            "per_page": 1,
            "select": OPENALEX_GRAPH_SELECT,
        },
    )
    if error:
        return None, error
    results = (data or {}).get("results") or []
    if not results:
        return None, "OpenAlex did not resolve the held-out DOI"
    return normalize_openalex_id(results[0].get("id")), None


def _openalex_direct_citers(
    parent_ids: set[str],
    *,
    remaining_nodes: int,
) -> tuple[set[str], str | None]:
    descendants: set[str] = set()
    ordered = sorted(parent_ids)
    for start in range(0, len(ordered), OPENALEX_GRAPH_BATCH_SIZE):
        batch = ordered[start : start + OPENALEX_GRAPH_BATCH_SIZE]
        cursor = "*"
        while cursor and len(descendants) < remaining_nodes:
            data, error = openalex_get(
                "/works",
                {
                    "filter": "cites:" + "|".join(batch),
                    "per_page": min(200, remaining_nodes - len(descendants)),
                    "cursor": cursor,
                    "select": OPENALEX_GRAPH_SELECT,
                },
            )
            if error:
                return descendants, error
            for work in (data or {}).get("results") or []:
                work_id = normalize_openalex_id(work.get("id"))
                if work_id:
                    descendants.add(work_id)
                    if len(descendants) >= remaining_nodes:
                        break
            cursor = ((data or {}).get("meta") or {}).get("next_cursor")
            if not ((data or {}).get("results") or []):
                break
        if len(descendants) >= remaining_nodes:
            break
    return descendants, None


def build_openalex_blocked_graph(identifiers: list[str]) -> tuple[frozenset[str], bool]:
    """Return target plus incoming citation descendants across configured hops."""
    doi = hidden_work_doi(identifiers)
    if not doi:
        return frozenset(), False
    now = time.time()
    with OPENALEX_GRAPH_LOCK:
        cached = OPENALEX_GRAPH_CACHE.get(doi)
        if cached and now - cached[0] < (
            OPENALEX_GRAPH_CACHE_TTL if cached[2] else OPENALEX_GRAPH_ERROR_TTL
        ):
            return cached[1], cached[2]

        target_id, error = _openalex_target_id(doi)
        if not target_id:
            LOGGER.warning("OpenAlex graph unavailable for %s: %s", doi, error)
            result = (now, frozenset(), False)
            OPENALEX_GRAPH_CACHE[doi] = result
            return result[1], result[2]

        max_depth = max(
            1,
            min(int(os.getenv("BIOEVAL_OPENALEX_DESCENDANT_DEPTH", "20")), 50),
        )
        max_nodes = max(
            1,
            min(int(os.getenv("BIOEVAL_OPENALEX_DESCENDANT_MAX_NODES", "10000")), 100000),
        )
        blocked = {target_id}
        frontier = {target_id}
        complete = True
        for _depth in range(max_depth):
            remaining = max_nodes - len(blocked)
            if remaining <= 0:
                complete = False
                break
            children, error = _openalex_direct_citers(
                frontier,
                remaining_nodes=remaining,
            )
            if error:
                LOGGER.warning("OpenAlex descendant traversal incomplete for %s: %s", doi, error)
                complete = False
                break
            frontier = children - blocked
            if not frontier:
                break
            blocked.update(frontier)
        else:
            if frontier:
                complete = False

        result = (now, frozenset(blocked), complete)
        OPENALEX_GRAPH_CACHE[doi] = result
        return result[1], result[2]


def openalex_graph_blocks(value: str | None, identifiers: list[str]) -> bool:
    work_id = normalize_openalex_id(value)
    if not work_id:
        doi = hidden_work_doi([value or ""])
        if doi:
            if doi not in OPENALEX_DOI_ID_CACHE:
                OPENALEX_DOI_ID_CACHE[doi], _error = _openalex_target_id(doi)
            work_id = OPENALEX_DOI_ID_CACHE.get(doi)
    if not work_id:
        return False
    blocked, complete = build_openalex_blocked_graph(identifiers)
    if not complete:
        LOGGER.warning("Blocking OpenAlex work because the hidden lineage graph is incomplete.")
        return True
    return work_id in blocked


def abstract_from_inverted_index(index: dict | None) -> str:
    if not isinstance(index, dict):
        return ""
    positioned_words: list[tuple[int, str]] = []
    for word, positions in index.items():
        if not isinstance(positions, list):
            continue
        for position in positions:
            if isinstance(position, int):
                positioned_words.append((position, str(word)))
    return " ".join(word for _, word in sorted(positioned_words))


def openalex_external_ids(work: dict) -> dict[str, str]:
    ids = work.get("ids") or {}
    external_ids: dict[str, str] = {}
    if work.get("id"):
        external_ids["OpenAlex"] = str(work["id"])
    doi = work.get("doi") or ids.get("doi")
    if doi:
        external_ids["DOI"] = str(doi)
    if ids.get("pmid"):
        external_ids["PMID"] = str(ids["pmid"])
    if ids.get("pmcid"):
        external_ids["PMCID"] = str(ids["pmcid"])
    return external_ids


def normalize_openalex_work(work: dict) -> dict:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return {
        "title": work.get("title") or work.get("display_name") or "",
        "year": work.get("publication_year"),
        "publicationDate": work.get("publication_date"),
        "venue": source.get("display_name") or "",
        "abstract": abstract_from_inverted_index(work.get("abstract_inverted_index")),
        "citationCount": work.get("cited_by_count", 0),
        "externalIds": openalex_external_ids(work),
        "openalexId": work.get("id") or "",
        "url": work.get("id") or "",
        "landingPageUrl": primary_location.get("landing_page_url") or "",
    }


def _after_external_cutoff(paper: dict, cutoff: str | None) -> bool:
    if not cutoff:
        return False
    try:
        limit = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
        if limit.tzinfo is None:
            limit = limit.replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    publication_date = paper.get("publicationDate")
    if publication_date:
        try:
            published = datetime.fromisoformat(str(publication_date)).replace(
                tzinfo=timezone.utc
            )
            return published > limit
        except ValueError:
            return True
    year = paper.get("year")
    if isinstance(year, int):
        return year >= limit.year
    return True


def _page_publication_date(text: str, headers: object) -> str | None:
    for pattern in (
        r'(?i)(?:datePublished|article:published_time|publication_date)'
        r'[^0-9]{0,80}(\d{4}-\d{2}-\d{2})',
        r'(?i)<time[^>]+datetime=["\'](\d{4}-\d{2}-\d{2})',
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    if text.lstrip().startswith("<?xml"):
        try:
            root = ET.fromstring(text)
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] != "pub-date":
                    continue
                values = {
                    child.tag.rsplit("}", 1)[-1]: (child.text or "").strip()
                    for child in element
                }
                if values.get("year") and values.get("month") and values.get("day"):
                    return (
                        f"{int(values['year']):04d}-{int(values['month']):02d}-"
                        f"{int(values['day']):02d}"
                    )
        except (ET.ParseError, ValueError):
            pass
    last_modified = headers.get("Last-Modified") if hasattr(headers, "get") else None
    if last_modified:
        try:
            return parsedate_to_datetime(last_modified).date().isoformat()
        except (TypeError, ValueError):
            return None
    return None


def openalex_search(query: str, limit: int) -> tuple[list[dict], list[str]]:
    params = {
        "search": query,
        "per_page": max(1, min(limit, 20)),
        "select": OPENALEX_WORK_SELECT,
    }
    data, error = openalex_get("/works", params)
    if data and data.get("results"):
        return [normalize_openalex_work(work) for work in data.get("results", [])], []
    return [], [error or "/works returned 0 results"]


def openalex_snippets(query: str, limit: int) -> tuple[list[dict], list[str]]:
    papers, diagnostics = openalex_search(query, limit)
    snippets = [
        {
            "paper": paper,
            "snippet": {
                "text": paper.get("abstract") or "",
                "section": "Abstract (OpenAlex metadata)",
            },
        }
        for paper in papers
        if paper.get("abstract")
    ]
    diagnostics.append("OpenAlex does not provide passage snippets; using abstract excerpts when available.")
    return snippets, diagnostics


def paper_matches_hidden_work(paper: dict, identifiers: list[str]) -> bool:
    if openalex_graph_blocks(
        paper.get("openalexId")
        or (paper.get("externalIds") or {}).get("OpenAlex")
        or paper.get("url"),
        identifiers,
    ):
        return True
    ext = paper.get("externalIds") or {}
    fields = [
        paper.get("title") or "",
        paper.get("abstract") or "",
        " ".join(str(v) for v in ext.values() if v),
    ]
    return contains_hidden_identifier("\n".join(fields), identifiers)


def snippet_matches_hidden_work(item: dict, identifiers: list[str]) -> bool:
    paper = item.get("paper") or {}
    if paper_matches_hidden_work(paper, identifiers):
        return True
    snippet = item.get("snippet") or {}
    fields = [
        paper.get("title") or "",
        " ".join(str(v) for v in (paper.get("externalIds") or {}).values() if v),
        snippet.get("text") or "",
    ]
    return contains_hidden_identifier("\n".join(fields), identifiers)


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
        abstract = paper.get("abstract") or ""
        summary = abstract[:500]
        search_link = paper.get("url") or openalex_web_search_url(title)
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
    lines = [f"# Abstract excerpt search results for {query!r}"]
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
            lines.append(text[:600])
    return "\n".join(lines)


def restricted_research_papers(
    *,
    operation: str,
    query: str,
    limit: int,
    identifiers: list[str],
    guard_model: str | None = None,
    guard_api_base: str | None = None,
    external_source_cutoff: str | None = None,
) -> dict:
    deny = deny_leaky_query(query, identifiers)
    if deny:
        return {"status": "denied", "error": deny}
    guard_reason = traffic_guard_blocks(
        kind="research_query",
        candidate={
            "operation": operation,
            "query": query,
            "external_source_cutoff": external_source_cutoff,
        },
        identifiers=identifiers,
        model=guard_model,
        api_base=guard_api_base,
    )
    if guard_reason:
        return {"status": "denied", "error": PUBLIC_GUARD_DENIAL}
    if operation == "snippet_search":
        snippets, diagnostics = openalex_snippets(query, limit)
        filtered = []
        blocked_by_guard_agent = 0
        for item in snippets:
            if snippet_matches_hidden_work(item, identifiers):
                continue
            paper = item.get("paper") or {}
            if _after_external_cutoff(paper, external_source_cutoff):
                continue
            snippet = item.get("snippet") or {}
            snippet_text = "\n".join(
                [
                    paper.get("title") or "",
                    " ".join(str(v) for v in (paper.get("externalIds") or {}).values() if v),
                    snippet.get("text") or "",
                ]
            )
            guard_reason = traffic_guard_blocks(
                kind="research_snippet_result",
                candidate={
                    "query": query,
                    "title": paper.get("title") or "",
                    "year": paper.get("year"),
                    "external_ids": paper.get("externalIds") or {},
                    "snippet": snippet.get("text") or "",
                    "section": snippet.get("section") or "",
                    "text_resource": make_guard_text_resource(
                        snippet_text,
                        "OpenAlex work metadata and abstract excerpt.",
                    ),
                },
                identifiers=identifiers,
                model=guard_model,
                api_base=guard_api_base,
            )
            if guard_reason:
                blocked_by_guard_agent += 1
                continue
            filtered.append(item)
        if snippets and not filtered:
            diagnostics.append("Some results were filtered and are not available.")
        if blocked_by_guard_agent:
            diagnostics.append(f"{blocked_by_guard_agent} result(s) were filtered.")
        if filtered:
            return {
                "status": "ok",
                "operation": operation,
                "count": len(filtered),
                "diagnostics": diagnostics,
                "content": format_snippets(filtered, query),
            }
    papers, diagnostics = openalex_search(query, limit)
    filtered = []
    blocked_by_guard_agent = 0
    for paper in papers:
        if _after_external_cutoff(paper, external_source_cutoff):
            continue
        if paper_matches_hidden_work(paper, identifiers):
            continue
        paper_text = "\n".join(
            [
                paper.get("title") or "",
                paper.get("venue") or "",
                " ".join(str(v) for v in (paper.get("externalIds") or {}).values() if v),
                paper.get("abstract") or "",
            ]
        )
        guard_reason = traffic_guard_blocks(
            kind="research_paper_result",
            candidate={
                "query": query,
                "title": paper.get("title") or "",
                "year": paper.get("year"),
                "venue": paper.get("venue") or "",
                "external_ids": paper.get("externalIds") or {},
                "abstract": (paper.get("abstract") or "")[:1200],
                "text_resource": make_guard_text_resource(
                    paper_text,
                    "OpenAlex paper result title, identifiers, venue, and abstract.",
                ),
            },
            identifiers=identifiers,
            model=guard_model,
            api_base=guard_api_base,
        )
        if guard_reason:
            blocked_by_guard_agent += 1
            continue
        filtered.append(paper)
    if papers and not filtered:
        diagnostics.append("Some results were filtered and are not available.")
    if blocked_by_guard_agent:
        diagnostics.append(f"{blocked_by_guard_agent} result(s) were filtered.")
    return {
        "status": "ok",
        "operation": operation,
        "count": len(filtered),
        "diagnostics": diagnostics,
        "content": format_results(filtered, query, diagnostics),
    }


def restricted_web_search(
    *,
    query: str,
    limit: int,
    allowed_domain: list[str] | None,
    blocked_domain: list[str] | None,
    identifiers: list[str],
    guard_model: str | None = None,
    guard_api_base: str | None = None,
    external_source_cutoff: str | None = None,
) -> dict:
    deny = deny_leaky_query(query, identifiers)
    if deny:
        return {"status": "denied", "error": deny}
    guard_reason = traffic_guard_blocks(
        kind="web_query",
        candidate={"query": query, "external_source_cutoff": external_source_cutoff},
        identifiers=identifiers,
        model=guard_model,
        api_base=guard_api_base,
    )
    if guard_reason:
        return {"status": "denied", "error": PUBLIC_GUARD_DENIAL}
    rows: list[dict] = []
    diagnostics: list[str] = []
    duckduckgo_error = None
    for attempt in range(2):
        try:
            resp = requests.get(duckduckgo_search_url(query), headers={"User-Agent": USER_AGENT}, timeout=20)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
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
    used_openalex_fallback = False
    if external_source_cutoff and rows:
        diagnostics.append(
            "Discarded undated general-web results under the external-source cutoff."
        )
        rows = []
    if not rows:
        diagnostics.append(f"DuckDuckGo search failed: {duckduckgo_error}" if duckduckgo_error else "DuckDuckGo returned 0 parsable external results")
        papers, openalex_diagnostics = openalex_search(query, limit)
        diagnostics.extend(openalex_diagnostics)
        rows = [
            {
                "title": paper.get("title") or "",
                "url": paper.get("url") or openalex_web_search_url(paper.get("title") or ""),
                "publicationDate": paper.get("publicationDate"),
                "year": paper.get("year"),
            }
            for paper in papers
        ]
        used_openalex_fallback = bool(rows)

    seen = set()
    allowed = {d.lower() for d in (allowed_domain or [])}
    blocked = {d.lower() for d in (blocked_domain or [])}
    blocked_by_guard = 0
    blocked_by_request = 0
    blocked_by_allowed = 0
    blocked_by_identifier = 0
    blocked_by_guard_agent = 0
    filtered: list[dict] = []
    for row in rows:
        if _after_external_cutoff(row, external_source_cutoff):
            blocked_by_guard += 1
            continue
        url = row["url"]
        if url in seen:
            continue
        if contains_hidden_identifier(f"{row.get('title', '')}\n{url}", identifiers):
            blocked_by_identifier += 1
            continue
        if blocked_url_reason(url, identifiers):
            blocked_by_guard += 1
            continue
        if allowed and not host_matches(url, allowed):
            blocked_by_allowed += 1
            continue
        if blocked and host_matches(url, blocked):
            blocked_by_request += 1
            continue
        guard_reason = traffic_guard_blocks(
            kind="web_search_result",
            candidate={
                "query": query,
                "title": row.get("title", ""),
                "url": url,
                "text_resource": make_guard_text_resource(
                    "\n".join([row.get("title", ""), url]),
                    "Web search result title and URL only; page text is not fetched yet.",
                ),
                "content_availability": (
                    "Only search-result title and URL are available at this stage. "
                    "If allowed and later fetched, fetch_url and fetched_page_content "
                    "guards inspect the URL and page text."
                ),
                "external_source_cutoff": external_source_cutoff,
            },
            identifiers=identifiers,
            model=guard_model,
            api_base=guard_api_base,
        )
        if guard_reason:
            blocked_by_guard_agent += 1
            continue
        seen.add(url)
        filtered.append(row)
        if len(filtered) >= max(1, min(limit, 20)):
            break

    if rows and not filtered:
        diagnostics.append(
            "Search returned candidate results, but none are available after filtering "
            f"(policy={blocked_by_guard + blocked_by_identifier + blocked_by_guard_agent}, "
            f"allowed-domain={blocked_by_allowed}, "
            f"blocked-domain={blocked_by_request})."
        )
    elif (
        blocked_by_guard
        or blocked_by_identifier
        or blocked_by_guard_agent
        or blocked_by_allowed
        or blocked_by_request
    ):
        diagnostics.append(
            f"Filtered candidates: policy={blocked_by_guard + blocked_by_identifier + blocked_by_guard_agent}, "
            f"allowed-domain={blocked_by_allowed}, "
            f"blocked-domain={blocked_by_request}."
        )
    text = "\n".join(f"{idx}. {row['title']}\n   {row['url']}" for idx, row in enumerate(filtered, start=1))
    if text and used_openalex_fallback:
        text += "\n(via OpenAlex academic fallback)"
    if not text and diagnostics:
        text = "No search results.\nDiagnostics:\n" + "\n".join(f"- {item}" for item in diagnostics)
    return {
        "status": "ok",
        "results": filtered,
        "counts": {
            "duckduckgo_candidates": duckduckgo_count,
            "total_candidates": len(rows),
            "returned": len(filtered),
            "blocked_by_guard": blocked_by_guard,
            "blocked_by_target_identifier": blocked_by_identifier,
            "blocked_by_traffic_guard": blocked_by_guard_agent,
            "blocked_by_allowed_domain": blocked_by_allowed,
            "blocked_by_requested_domain": blocked_by_request,
        },
        "diagnostics": diagnostics,
        "content": text or "No search results.",
    }


@dataclass
class _SafeWebResponse:
    status_code: int
    headers: object
    url: str
    text: str


def _safe_web_get(url: str) -> _SafeWebResponse:
    request = urllib.request.Request(url, headers=FETCH_HEADERS)
    with _safe_urlopen(request, timeout=30) as response:
        payload = response.read(MAX_FETCH_BYTES + 1)
        if len(payload) > MAX_FETCH_BYTES:
            raise ValueError("remote page exceeds the safe fetch byte limit")
        charset = response.headers.get_content_charset() or "utf-8"
        return _SafeWebResponse(
            status_code=response.status,
            headers=response.headers,
            url=response.geturl(),
            text=payload.decode(charset, errors="replace"),
        )


def restricted_fetch_webpage(
    *,
    url: str,
    max_chars: int,
    identifiers: list[str],
    guard_model: str | None = None,
    guard_api_base: str | None = None,
    external_source_cutoff: str | None = None,
) -> dict:
    try:
        _validate_public_url(url)
    except ValueError:
        return {"status": "denied", "error": "URL must resolve to a public HTTPS address."}
    reason = blocked_url_reason(url, identifiers)
    if reason:
        return {"status": "denied", "error": reason}
    guard_reason = traffic_guard_blocks(
        kind="fetch_url",
        candidate={"url": url, "external_source_cutoff": external_source_cutoff},
        identifiers=identifiers,
        model=guard_model,
        api_base=guard_api_base,
    )
    if guard_reason:
        return {"status": "denied", "error": PUBLIC_GUARD_DENIAL}
    fetch_url = pmc_eutils_url(url) or url
    try:
        resp = _safe_web_get(fetch_url)
    except (ValueError, OSError, urllib.error.URLError):
        return {"status": "denied", "error": "URL could not be fetched safely."}
    if resp.status_code == 403:
        return {
            "status": "error",
            "error": (
                "remote site returned HTTP 403 Forbidden, likely blocking automated fetches; "
                "try research_papers/web_search metadata or another accessible source"
            ),
        }
    if resp.status_code == 404:
        return {"status": "error", "error": "remote site returned HTTP 404 Not Found"}
    if resp.status_code >= 400:
        return {"status": "error", "error": f"remote site returned HTTP {resp.status_code}"}
    final_url = url if fetch_url != url else resp.url
    reason = blocked_url_reason(final_url, identifiers)
    if reason:
        return {"status": "denied", "error": reason}
    if final_url != url:
        guard_reason = traffic_guard_blocks(
            kind="fetch_url",
            candidate={
                "url": final_url,
                "redirected_from": url,
                "external_source_cutoff": external_source_cutoff,
            },
            identifiers=identifiers,
            model=guard_model,
            api_base=guard_api_base,
        )
        if guard_reason:
            return {"status": "denied", "error": PUBLIC_GUARD_DENIAL}
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" in content_type or "octet-stream" in content_type:
        raise ValueError("binary/PDF content is not fetchable through this text tool")
    response_text = resp.text
    publication_date = _page_publication_date(response_text, resp.headers)
    if external_source_cutoff and _after_external_cutoff(
        {"publicationDate": publication_date},
        external_source_cutoff,
    ):
        return {
            "status": "denied",
            "error": "Page date is unavailable or later than the external-source cutoff.",
        }
    if "xml" in content_type or response_text.lstrip().startswith("<?xml"):
        text = extract_nlm_xml_text(response_text)
        if not text:
            extractor = TextExtractor()
            extractor.feed(response_text)
            text = extractor.text()
    elif "html" in content_type or not content_type:
        extractor = TextExtractor()
        extractor.feed(response_text)
        text = extractor.text()
    else:
        text = response_text
    if looks_like_bot_challenge(text):
        return {
            "status": "error",
            "error": (
                "remote site returned an anti-bot challenge page instead of readable content; "
                "try research_papers/web_search metadata or another accessible source"
            ),
        }
    if contains_hidden_identifier(f"{final_url}\n{text}", identifiers):
        return {
            "status": "denied",
            "error": PUBLIC_GUARD_DENIAL,
        }
    guard_reason = traffic_guard_blocks(
        kind="fetched_page_content",
        candidate={
            "url": final_url,
            "content_type": content_type,
            "external_source_cutoff": external_source_cutoff,
            "text_resource": make_guard_text_resource(
                "\n".join([final_url, text]),
                "Fetched webpage URL and extracted page text.",
            ),
        },
        identifiers=identifiers,
        model=guard_model,
        api_base=guard_api_base,
    )
    if guard_reason:
        return {"status": "denied", "error": PUBLIC_GUARD_DENIAL}
    return {
        "status": "ok",
        "url": final_url,
        "content_type": content_type,
        "publication_date": publication_date,
        "text": text[:max_chars],
    }
