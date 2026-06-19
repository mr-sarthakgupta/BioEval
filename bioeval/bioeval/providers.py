"""Real online dataset acquisition for the data-agent.

These helpers download from public sources (Zenodo, figshare, or arbitrary URLs)
into a host-side staging directory. Everything fetched here still passes through
`bioeval.guard` before it is exposed to the UEA, so a provider can never be a
back door around the leak boundary.
"""

from __future__ import annotations

import fnmatch
import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "bioeval-data-agent/0.2"
DEFAULT_TIMEOUT = int(os.getenv("BIOEVAL_FETCH_TIMEOUT", "120"))
METADATA_TIMEOUT = 30


@dataclass
class FetchedFile:
    path: Path
    bytes: int
    url: str


def _matches(name: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return True
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _excluded(name: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    return any(fnmatch.fnmatch(name, p) for p in patterns)


def _download(url: str, dest: Path, *, max_bytes: int | None = None) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        if max_bytes is not None:
            length = resp.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise ValueError(
                    f"Remote file {url} is {int(length)} bytes, over the {max_bytes} budget."
                )
        data = resp.read()
    if max_bytes is not None and len(data) > max_bytes:
        raise ValueError(f"Downloaded file from {url} exceeds the {max_bytes} byte budget.")
    dest.write_bytes(data)
    return len(data)


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=METADATA_TIMEOUT) as resp:
        return json.loads(resp.read())


def fetch_zenodo(
    record_id: str,
    dest_dir: Path,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    max_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> list[FetchedFile]:
    meta = _get_json(f"https://zenodo.org/api/records/{record_id}")
    out: list[FetchedFile] = []
    total = 0
    for f in meta.get("files", []):
        name = f.get("key", "")
        if not _matches(name, include) or _excluded(name, exclude):
            continue
        size = int(f.get("size") or 0)
        if max_bytes is not None and size and size > max_bytes:
            continue
        if max_total_bytes is not None and size and total + size > max_total_bytes:
            continue
        url = f.get("links", {}).get("self") or f.get("links", {}).get("download")
        if not url:
            continue
        n = _download(url, dest_dir / name, max_bytes=max_bytes)
        total += n
        out.append(FetchedFile(path=dest_dir / name, bytes=n, url=url))
    return out


def fetch_figshare(
    article_id: str,
    dest_dir: Path,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    max_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> list[FetchedFile]:
    meta = _get_json(f"https://api.figshare.com/v2/articles/{article_id}")
    out: list[FetchedFile] = []
    total = 0
    for f in meta.get("files", []):
        name = f.get("name", "")
        if not _matches(name, include) or _excluded(name, exclude):
            continue
        size = int(f.get("size") or 0)
        if max_bytes is not None and size and size > max_bytes:
            continue
        if max_total_bytes is not None and size and total + size > max_total_bytes:
            continue
        url = f.get("download_url")
        if not url:
            continue
        n = _download(url, dest_dir / name, max_bytes=max_bytes)
        total += n
        out.append(FetchedFile(path=dest_dir / name, bytes=n, url=url))
    return out


def fetch_url(url: str, dest_dir: Path, *, max_bytes: int | None = None) -> list[FetchedFile]:
    name = url.rstrip("/").split("/")[-1] or "download"
    n = _download(url, dest_dir / name, max_bytes=max_bytes)
    return [FetchedFile(path=dest_dir / name, bytes=n, url=url)]


def fetch_online_spec(
    online: dict,
    dest_dir: Path,
    *,
    max_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> list[FetchedFile]:
    """Dispatch an `online:` catalog spec to the right provider."""
    provider = (online or {}).get("provider")
    include = online.get("include")
    exclude = online.get("exclude")
    if provider == "zenodo":
        return fetch_zenodo(
            str(online["record_id"]),
            dest_dir,
            include=include,
            exclude=exclude,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
        )
    if provider == "figshare":
        return fetch_figshare(
            str(online["article_id"]),
            dest_dir,
            include=include,
            exclude=exclude,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
        )
    if provider == "url":
        return fetch_url(str(online["url"]), dest_dir, max_bytes=max_bytes)
    raise ValueError(f"Unsupported online provider: {provider!r}")
