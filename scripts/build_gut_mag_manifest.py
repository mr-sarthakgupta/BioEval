#!/usr/bin/env python3
"""Pin the ENA representative-genome inventory and deterministic pilot subset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import urllib.parse
import urllib.request
from pathlib import Path


PROJECT = "PRJEB31003"
EXPECTED_ROWS = 2058
EXPECTED_BASES = 4_462_286_565
PILOT_SIZE = 256
FIELDS = (
    "accession",
    "assembly_accession",
    "base_count",
    "first_public",
    "set_fasta_ftp",
)


def fetch_inventory() -> list[dict[str, str]]:
    params = {
        "result": "wgs_set",
        "query": f'study_accession="{PROJECT}"',
        "fields": ",".join(FIELDS),
        "format": "json",
        "limit": "0",
    }
    url = "https://www.ebi.ac.uk/ena/portal/api/search?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={"User-Agent": "paper-invert/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        rows = json.load(response)
    if not isinstance(rows, list):
        raise SystemExit("ENA inventory response was not a list.")
    return rows


def pilot_rank(accession: str) -> str:
    return hashlib.sha256(f"bioeval-gut-mag-v1:{accession}".encode()).hexdigest()


def build(output: Path) -> None:
    rows = fetch_inventory()
    rows.sort(key=lambda row: row["accession"])
    if len(rows) != EXPECTED_ROWS:
        raise SystemExit(f"Expected {EXPECTED_ROWS} sequence sets; received {len(rows)}.")
    total_bases = sum(int(row["base_count"]) for row in rows)
    if total_bases != EXPECTED_BASES:
        raise SystemExit(f"Expected {EXPECTED_BASES} bases; received {total_bases}.")
    if any(not row.get("set_fasta_ftp") for row in rows):
        raise SystemExit("Every sequence set must have a FASTA URL.")

    output.mkdir(parents=True, exist_ok=True)
    inventory_path = output / "ena_sequence_manifest.csv"
    with inventory_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in FIELDS} for row in rows)

    selected = sorted(rows, key=lambda row: pilot_rank(row["accession"]))[:PILOT_SIZE]
    pilot_path = output / "pilot_selection.csv"
    with pilot_path.open("w", newline="", encoding="utf-8") as handle:
        fields = ("opaque_genome_id", "accession", "assembly_accession", "base_count", "fasta_url")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(selected, start=1):
            writer.writerow(
                {
                    "opaque_genome_id": f"genome_{index:04d}",
                    "accession": row["accession"],
                    "assembly_accession": row["assembly_accession"],
                    "base_count": row["base_count"],
                    "fasta_url": "https://" + row["set_fasta_ftp"],
                }
            )

    metadata = {
        "project": PROJECT,
        "sequence_set_first_public_min": min(row["first_public"] for row in rows),
        "sequence_set_first_public_max": max(row["first_public"] for row in rows),
        "sequence_sets": len(rows),
        "total_bases": total_bases,
        "pilot_size": len(selected),
        "selection": "lowest SHA-256 values for bioeval-gut-mag-v1:<wgs_accession>",
        "representative_pilot_downloaded": False,
        "grantable": False,
        "blocked_reason": (
            "Author-selected one-per-discovered-OTU representatives encode "
            "the target selection result."
        ),
    }
    (output / "source_manifest.json").write_text(
        json.dumps(metadata, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "problems_imcomplete"
            / "s41586-019-1058-x_gut-mag-diversity"
            / "evaluator"
            / "host-audit"
        ),
    )
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
