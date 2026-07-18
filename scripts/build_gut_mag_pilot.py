#!/usr/bin/env python3
"""Build a host-only audit pilot from answer-bearing representative genomes."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


PROBLEM_ID = "s41586-019-1058-x_gut-mag-diversity"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(row: dict[str, str]) -> tuple[dict[str, str], bytes, str]:
    request = urllib.request.Request(
        row["fasta_url"],
        headers={"User-Agent": "paper-invert/1.0"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        compressed = response.read()
    return row, compressed, hashlib.md5(compressed).hexdigest()  # noqa: S324


def anonymize_one(
    row: dict[str, str],
    compressed: bytes,
    output: gzip.GzipFile,
) -> tuple[int, int]:
    contigs = 0
    bases = 0
    sequence_parts: list[bytes] = []

    def flush_sequence() -> None:
        nonlocal bases
        if not sequence_parts:
            return
        sequence = b"".join(sequence_parts).replace(b" ", b"").upper()
        bases += len(sequence)
        for offset in range(0, len(sequence), 80):
            output.write(sequence[offset : offset + 80] + b"\n")
        sequence_parts.clear()

    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as source:
        for raw_line in source:
            line = raw_line.strip()
            if line.startswith(b">"):
                flush_sequence()
                contigs += 1
                output.write(
                    f">{row['opaque_genome_id']}_contig_{contigs:05d}\n".encode()
                )
            elif line:
                sequence_parts.append(line)
        flush_sequence()
    return contigs, bases


def build(problem_root: Path, workers: int) -> None:
    audit_root = problem_root / "evaluator" / "host-audit"
    output_dir = audit_root / "pilot-fastas"
    output_dir.mkdir(parents=True, exist_ok=True)

    with (audit_root / "pilot_selection.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 256:
        raise SystemExit(f"Expected 256 selected genomes; received {len(rows)}.")

    sequence_path = output_dir / "pilot_sequences.fna.gz"
    metadata_path = audit_root / "pilot_metadata.csv"
    source_map_path = audit_root / "pilot_source_mapping.csv"
    metadata: list[dict[str, object]] = []
    source_map: list[dict[str, object]] = []

    with sequence_path.open("wb") as raw_output:
        with gzip.GzipFile(
            fileobj=raw_output,
            mode="wb",
            compresslevel=6,
            mtime=0,
        ) as output:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for row, compressed, source_md5 in pool.map(download, rows):
                    contigs, bases = anonymize_one(row, compressed, output)
                    expected_bases = int(row["base_count"])
                    if bases != expected_bases:
                        raise SystemExit(
                            f"{row['opaque_genome_id']}: expected {expected_bases} bases, "
                            f"got {bases}."
                        )
                    metadata.append(
                        {
                            "opaque_genome_id": row["opaque_genome_id"],
                            "assembly_bases": bases,
                            "contig_count": contigs,
                        }
                    )
                    source_map.append(
                        {
                            "opaque_genome_id": row["opaque_genome_id"],
                            "accession": row["accession"],
                            "assembly_accession": row["assembly_accession"],
                            "source_md5": source_md5,
                        }
                    )

    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("opaque_genome_id", "assembly_bases", "contig_count"),
        )
        writer.writeheader()
        writer.writerows(metadata)
    with source_map_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "opaque_genome_id",
                "accession",
                "assembly_accession",
                "source_md5",
            ),
        )
        writer.writeheader()
        writer.writerows(source_map)

    manifest = {
        "schema_version": "1.0",
        "genomes": len(metadata),
        "total_bases": sum(int(row["assembly_bases"]) for row in metadata),
        "total_contigs": sum(int(row["contig_count"]) for row in metadata),
        "header_policy": "opaque genome and sequential contig identifiers only",
        "outputs": [
            {
                "path": str(path.relative_to(audit_root)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in (sequence_path, metadata_path)
        ],
    }
    (audit_root / "pilot_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    source_manifest_path = audit_root / "source_manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    source_manifest["representative_pilot_downloaded"] = True
    source_manifest_path.write_text(
        json.dumps(source_manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--allow-answer-bearing-host-audit",
        action="store_true",
        help="Acknowledge that PRJEB31003 contains author-selected representatives.",
    )
    args = parser.parse_args()
    if not args.allow_answer_bearing_host_audit:
        raise SystemExit(
            "Refusing to build a grantable pilot: PRJEB31003 contains "
            "answer-bearing author-selected representatives. Pass "
            "--allow-answer-bearing-host-audit only for host-side provenance work."
        )
    build(root / "problems_imcomplete" / PROBLEM_ID, args.workers)


if __name__ == "__main__":
    main()
