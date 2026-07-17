"""Real online dataset discovery and acquisition for the experiment-agent.

These helpers download from public sources (Zenodo, figshare, or arbitrary URLs)
into a host-side staging directory. Everything fetched here still passes through
`bioeval.guard` before it is exposed to the UEA, so a provider can never be a
back door around the leak boundary.
"""

from __future__ import annotations

import fnmatch
import http.client
import ipaddress
import json
import os
import socket
import ssl
import urllib.request
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

USER_AGENT = "bioeval-experiment-agent/1.0"
DEFAULT_TIMEOUT = int(os.getenv("BIOEVAL_FETCH_TIMEOUT", "120"))
METADATA_TIMEOUT = 30
DISCOVERY_INCLUDE = [
    "*.csv",
    "*.tsv",
    "*.txt",
    "*.parquet",
    "*.xlsx",
    "*.rds",
    "*.RDS",
    "*.fasta",
    "*.fa",
    "*.fastq.gz",
]
DISCOVERY_EXCLUDE = [
    "README*",
    "metadata.json",
    "*.pdf",
    "*.doc*",
    "*.md",
    "*.py",
    "*.R",
    "*.ipynb",
    "*.pkl",
    "*.h5",
    "*.hdf5",
    "*result*",
    "*figure*",
    "*model*",
]


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


def _validate_public_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Online dataset URLs must be unauthenticated HTTPS URLs.")
    host = parsed.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("Online dataset URL resolves to a local host.")
    try:
        addresses = {
            info[4][0]
            for info in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except OSError as exc:
        raise ValueError("Online dataset host could not be resolved safely.") from exc
    if not addresses:
        raise ValueError("Online dataset host has no resolved address.")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError("Online dataset URL resolves to a non-public address.")


def _public_addresses(url: str) -> tuple[str, int, tuple[str, ...]]:
    _validate_public_url(url)
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or 443
    addresses = sorted(
        {
            info[4][0]
            for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            if ipaddress.ip_address(info[4][0]).is_global
        }
    )
    if not addresses:
        raise ValueError("Online dataset host has no public address.")
    return host, port, tuple(addresses)


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, *, pinned_addresses: tuple[str, ...], **kwargs):
        self._pinned_addresses = pinned_addresses
        super().__init__(host, **kwargs)

    def connect(self) -> None:
        last_error: OSError | None = None
        for address in self._pinned_addresses:
            try:
                sock = socket.create_connection(
                    (address, self.port),
                    self.timeout,
                    self.source_address,
                )
                self.sock = self._context.wrap_socket(
                    sock,
                    server_hostname=self.host,
                )
                return
            except OSError as exc:
                last_error = exc
        raise OSError("Could not connect to a pinned public address.") from last_error


class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        _host, _port, addresses = _public_addresses(req.full_url)

        def connection_factory(host, **kwargs):
            kwargs.setdefault("context", ssl.create_default_context())
            return _PinnedHTTPSConnection(
                host,
                pinned_addresses=addresses,
                **kwargs,
            )

        return self.do_open(connection_factory, req)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _safe_urlopen(req: urllib.request.Request, *, timeout: int):
    _validate_public_url(req.full_url)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        _PinnedHTTPSHandler(),
        _SafeRedirectHandler(),
    )
    return opener.open(req, timeout=timeout)


def _safe_destination(dest_dir: Path, name: str) -> Path:
    if not name or Path(name).is_absolute() or Path(name).name != name:
        raise ValueError("Provider filename is not a safe basename.")
    destination = (dest_dir / name).resolve()
    destination.relative_to(dest_dir.resolve())
    return destination


def _download(
    url: str,
    dest: Path,
    *,
    max_bytes: int | None = None,
    headers: dict[str, str] | None = None,
) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, **(headers or {})},
    )
    try:
        with _safe_urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            _validate_public_url(resp.geturl())
            if max_bytes is not None:
                length = resp.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise ValueError(
                        f"Remote file {url} is {int(length)} bytes, over the {max_bytes} budget."
                    )
            total = 0
            with dest.open("wb") as fh:
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise ValueError(
                            f"Downloaded file from {url} exceeds the {max_bytes} byte budget."
                        )
                    fh.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return total


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with _safe_urlopen(req, timeout=METADATA_TIMEOUT) as resp:
        return json.loads(resp.read())


def _post_json(url: str, payload: dict) -> list[dict]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        method="POST",
    )
    with _safe_urlopen(req, timeout=METADATA_TIMEOUT) as resp:
        value = json.loads(resp.read())
    return value if isinstance(value, list) else []


def discover_dataset_specs(query: str, *, limit: int = 5) -> list[dict]:
    """Search allowlisted repositories for metadata-only dataset candidates."""
    if os.getenv("BIOEVAL_ONLINE_DATA_DISCOVERY", "1").lower() in {
        "0",
        "false",
        "off",
        "none",
    }:
        return []
    candidates: list[dict] = []
    encoded = urllib.parse.quote(query[:1000])
    try:
        zenodo = _get_json(
            f"https://zenodo.org/api/records?q={encoded}&type=dataset&size={limit}"
        )
        for item in zenodo.get("hits", {}).get("hits", []):
            metadata = item.get("metadata", {})
            files = item.get("files", [])
            candidates.append(
                {
                    "id": f"online_zenodo_{item.get('id')}",
                    "description": " ".join(
                        str(value)
                        for value in [
                            metadata.get("title"),
                            metadata.get("description"),
                            " ".join(metadata.get("keywords") or []),
                        ]
                        if value
                    )[:4000],
                    "modalities": ["online", "dataset"],
                    "approx_bytes": sum(int(file.get("size") or 0) for file in files),
                    "online": {
                        "provider": "zenodo",
                        "record_id": str(item.get("id")),
                        "include": DISCOVERY_INCLUDE,
                        "exclude": DISCOVERY_EXCLUDE,
                    },
                }
            )
    except Exception:
        pass
    try:
        figshare = _post_json(
            "https://api.figshare.com/v2/articles/search",
            {
                "search_for": query[:1000],
                "item_type": 3,
                "limit": limit,
                "order": "published_date",
                "order_direction": "desc",
            },
        )
        for item in figshare:
            candidates.append(
                {
                    "id": f"online_figshare_{item.get('id')}",
                    "description": " ".join(
                        str(value)
                        for value in [item.get("title"), item.get("description")]
                        if value
                    )[:4000],
                    "modalities": ["online", "dataset"],
                    "approx_bytes": None,
                    "online": {
                        "provider": "figshare",
                        "article_id": str(item.get("id")),
                        "include": DISCOVERY_INCLUDE,
                        "exclude": DISCOVERY_EXCLUDE,
                    },
                }
            )
    except Exception:
        pass
    return candidates[: limit * 2]


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
        destination = _safe_destination(dest_dir, name)
        n = _download(url, destination, max_bytes=max_bytes)
        total += n
        out.append(FetchedFile(path=destination, bytes=n, url=url))
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
        destination = _safe_destination(dest_dir, name)
        n = _download(url, destination, max_bytes=max_bytes)
        total += n
        out.append(FetchedFile(path=destination, bytes=n, url=url))
    return out


def fetch_dryad(
    version_id: str,
    dest_dir: Path,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    max_bytes: int | None = None,
    max_total_bytes: int | None = None,
) -> list[FetchedFile]:
    meta = _get_json(f"https://datadryad.org/api/v2/versions/{version_id}/files")
    files = meta.get("_embedded", {}).get("stash:files", [])
    token = os.getenv("DRYAD_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    out: list[FetchedFile] = []
    total = 0
    for item in files:
        name = Path(str(item.get("path", ""))).name
        if not _matches(name, include) or _excluded(name, exclude):
            continue
        size = int(item.get("size") or 0)
        if max_bytes is not None and size and size > max_bytes:
            continue
        if max_total_bytes is not None and size and total + size > max_total_bytes:
            continue
        relative_url = item.get("_links", {}).get("stash:download", {}).get("href")
        if not relative_url:
            continue
        url = urllib.parse.urljoin("https://datadryad.org", relative_url)
        destination = _safe_destination(dest_dir, name)
        n = _download(url, destination, max_bytes=max_bytes, headers=headers)
        total += n
        out.append(FetchedFile(path=destination, bytes=n, url=url))
    return out


def fetch_url(url: str, dest_dir: Path, *, max_bytes: int | None = None) -> list[FetchedFile]:
    name = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).name or "download"
    destination = _safe_destination(dest_dir, name)
    n = _download(url, destination, max_bytes=max_bytes)
    return [FetchedFile(path=destination, bytes=n, url=url)]


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
    if provider == "dryad":
        return fetch_dryad(
            str(online["version_id"]),
            dest_dir,
            include=include,
            exclude=exclude,
            max_bytes=max_bytes,
            max_total_bytes=max_total_bytes,
        )
    if provider == "url":
        return fetch_url(str(online["url"]), dest_dir, max_bytes=max_bytes)
    raise ValueError(f"Unsupported online provider: {provider!r}")
