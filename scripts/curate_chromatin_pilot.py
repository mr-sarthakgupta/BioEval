#!/usr/bin/env python3
"""Freeze the neutral metadata and binning protocol for the chromatin pilot."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "nature09906_chromatin-state-dynamics"
DATA = PROBLEM / "data"
CURATED = PROBLEM / "curated"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    lock_path = DATA / "acquired-pilot-sha256.csv"
    with lock_path.open(newline="", encoding="utf-8") as handle:
        acquired = list(csv.DictReader(handle))
    if len(acquired) != 6:
        raise RuntimeError("Chromatin pilot requires exactly six acquired tracks.")

    CURATED.mkdir(parents=True, exist_ok=True)
    track_map = CURATED / "pilot_track_map.csv"
    rows: list[dict[str, str]] = []
    for row in acquired:
        name = row["name"]
        cell_type = "H1" if "_H1_" in name else "K562"
        if "_H3K27me3_" in name:
            assay = "H3K27me3"
        elif "_H3K4me3_" in name:
            assay = "H3K4me3"
        elif "_WCE_" in name:
            assay = "WCE"
        else:
            raise RuntimeError(f"Unexpected pilot assay filename: {name}")
        rows.append(
            {
                "track_id": f"{cell_type}_{assay}",
                "filename": name,
                "cell_type": cell_type,
                "assay": assay,
                "bytes": row["bytes"],
                "sha256": row["sha256"],
            }
        )
    with track_map.open("w", newline="", encoding="utf-8") as handle:
        fields = ["track_id", "filename", "cell_type", "assay", "bytes", "sha256"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    protocol = CURATED / "pilot_binning_protocol.csv"
    with protocol.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parameter", "value"])
        writer.writerows(
            [
                ("chromosomes", "chr21;chr22"),
                ("bin_size_bp", "1000000"),
                ("read_assignment", "interval_midpoint"),
                ("normalization", "reads_per_million_pilot_reads"),
                ("pseudocount_rpm", "1"),
                ("enrichment", "log2((mark_rpm+1)/(matched_wce_rpm+1))"),
            ]
        )

    manifest = {
        "scope": "H1 and K562; H3K4me3, H3K27me3, and WCE; chr21 and chr22",
        "outputs": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in (track_map, protocol)
        ],
    }
    (CURATED / "pilot_input_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Wrote chromatin pilot metadata and binning protocol.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
