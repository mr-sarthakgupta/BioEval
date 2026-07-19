#!/usr/bin/env python3
"""Extract the neutral TraceBIND tutorial fragments and peak intervals only."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41467-026-73164-3_tracebind-atac-footprinting"
ARCHIVE = PROBLEM / "data" / "external" / "dropbox" / "tracebind-tutorial-archive.zip"
CURATED = PROBLEM / "curated"
PEAK_MEMBER = "footprints_identification/peaks_region_subset.txt"
FRAGMENT_MEMBER = "footprints_identification/atac_fragments_subset.tsv.gz"


def barcode_key(value: str) -> str:
    digest = hashlib.sha256(
        f"bioeval-tracebind-v1:{value}".encode("utf-8")
    ).hexdigest()[:12]
    return f"cell_{digest}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    CURATED.mkdir(parents=True, exist_ok=True)
    peaks_path = CURATED / "pilot_peaks.csv"
    fragments_path = CURATED / "pilot_fragments.csv.gz"
    with zipfile.ZipFile(ARCHIVE) as archive:
        peak_text = archive.read(PEAK_MEMBER).decode("utf-8")
        with peaks_path.open("w", newline="", encoding="utf-8") as output:
            writer = csv.writer(output)
            writer.writerow(["peak_id", "chromosome", "start", "end"])
            for row in csv.reader(io.StringIO(peak_text), delimiter=" ", skipinitialspace=True):
                if not row or row[0] == "chr":
                    continue
                writer.writerow([row[0], row[1], int(row[2]), int(row[3])])
        with (
            archive.open(FRAGMENT_MEMBER) as compressed,
            gzip.open(compressed, "rt") as source,
            gzip.open(fragments_path, "wt", newline="", encoding="utf-8") as output,
        ):
            reader = csv.reader(source, delimiter="\t")
            writer = csv.writer(output)
            writer.writerow(["chromosome", "start", "end", "cell_key", "count"])
            next(reader)
            for chromosome, start, end, barcode, count in reader:
                writer.writerow(
                    [chromosome, int(start), int(end), barcode_key(barcode), int(count)]
                )
    files = [peaks_path, fragments_path]
    manifest = {
        "source_archive_sha256": file_sha256(ARCHIVE),
        "members": [PEAK_MEMBER, FRAGMENT_MEMBER],
        "files": {
            path.name: {
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in files
        },
    }
    (CURATED / "pilot_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print("Wrote neutral TraceBIND peak and fragment pilot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
