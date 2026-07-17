#!/usr/bin/env python3
"""Acquire only files declared by the tracked GSE26386 manifests."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import sys
import tempfile
import urllib.request
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "bioeval"))
from bioeval.providers import _safe_urlopen  # noqa: E402

CORE_MANIFEST = HERE / "curated" / "core_bed_manifest.csv"
CEL_MANIFEST = HERE / "curated" / "expression_cel_manifest.csv"
USER_AGENT = "paper-invert/1.0"
PILOT_CHROMS = {"chr21", "chr22"}
PILOT_ACCESSIONS = {
    "GSM646337",  # H1 H3K27me3
    "GSM646345",  # H1 H3K4me3
    "GSM646352",  # H1 WCE
    "GSM646436",  # K562 H3K27me3
    "GSM646445",  # K562 H3K4me3
    "GSM646453",  # K562 WCE
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected: int, remaining: int) -> tuple[int, str]:
    if expected > remaining:
        raise RuntimeError(f"download budget exceeded before {destination.name}")
    if destination.exists() and destination.stat().st_size == expected:
        return 0, file_sha256(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    total = 0
    with _safe_urlopen(request, timeout=600) as source, destination.open("wb") as target:
        while chunk := source.read(1024 * 1024):
            total += len(chunk)
            if total > expected or total > remaining:
                destination.unlink(missing_ok=True)
                raise RuntimeError(f"size or download budget exceeded for {destination.name}")
            target.write(chunk)
    if total != expected:
        destination.unlink(missing_ok=True)
        raise RuntimeError(f"size mismatch for {destination.name}: {total} != {expected}")
    return total, file_sha256(destination)


def filter_bed(source_gz: Path, destination_gz: Path) -> str:
    destination_gz.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(source_gz, "rt", errors="replace") as source, gzip.open(
        destination_gz, "wt"
    ) as target:
        for line in source:
            if line.split("\t", 1)[0] in PILOT_CHROMS:
                target.write(line)
    return file_sha256(destination_gz)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("manifest-only", "pilot", "full"), required=True)
    parser.add_argument("--output", type=Path, default=HERE / "data")
    parser.add_argument("--max-download-bytes", type=int)
    args = parser.parse_args()

    core = rows(CORE_MANIFEST)
    cel = rows(CEL_MANIFEST)
    if len(core) != 178 or len(cel) != 19:
        raise RuntimeError("tracked manifest cardinality changed")
    if args.profile == "manifest-only":
        print("Validated 178 core BED and 19 CEL manifest rows; downloaded 0 bytes.")
        return 0

    selected = core if args.profile == "full" else [
        row for row in core if row["accession"] in PILOT_ACCESSIONS
    ]
    max_download_bytes = args.max_download_bytes or (
        45_000_000_000 if args.profile == "full" else 1_200_000_000
    )
    declared_bytes = sum(int(row["bytes"]) for row in selected)
    if args.profile == "full":
        declared_bytes += sum(int(row["bytes"]) for row in cel)
    if declared_bytes > max_download_bytes:
        raise RuntimeError(
            f"profile declares {declared_bytes} transfer bytes, above budget "
            f"{max_download_bytes}"
        )
    spent = 0
    acquired: list[dict[str, str | int]] = []
    with tempfile.TemporaryDirectory(prefix="bioeval-chromatin-") as tmp:
        temporary = Path(tmp)
        for row in selected:
            expected = int(row["bytes"])
            if args.profile == "full":
                destination = args.output / "core-bed" / row["name"]
                transferred, digest = download(
                    row["url"], destination, expected, max_download_bytes - spent
                )
                spent += transferred
            else:
                compressed = temporary / row["name"]
                transferred, _source_digest = download(
                    row["url"], compressed, expected, max_download_bytes - spent
                )
                spent += transferred
                destination = args.output / "pilot-h1-k562-chr21-chr22" / row["name"]
                digest = filter_bed(
                    compressed,
                    destination,
                )
            acquired.append(
                {
                    "accession": row["accession"],
                    "name": row["name"],
                    "bytes": destination.stat().st_size,
                    "sha256": digest,
                }
            )

        if args.profile == "full":
            for row in cel:
                expected = int(row["bytes"])
                destination = args.output / "expression-cel" / row["name"]
                transferred, digest = download(
                    row["url"], destination, expected, max_download_bytes - spent
                )
                spent += transferred
                acquired.append(
                    {
                        "accession": row["accession"],
                        "name": row["name"],
                        "bytes": destination.stat().st_size,
                        "sha256": digest,
                    }
                )

    lock_path = args.output / f"acquired-{args.profile}-sha256.csv"
    with lock_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["accession", "name", "bytes", "sha256"],
        )
        writer.writeheader()
        writer.writerows(acquired)
    print(f"Profile {args.profile}: transferred {spent} bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
