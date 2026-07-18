#!/usr/bin/env python3
"""Build frozen construct-family folds for the protein resistance libraries."""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_imcomplete" / "s41586-023-06328-6_protein-protease-resistance"
SOURCE = PROBLEM / "data" / "primary-observations" / "ngs-counts"
OUTPUT = PROBLEM / "curated" / "protein_group_folds.csv"
MUTATION_SUFFIX = re.compile(
    r"(?:_(?:del)?[A-Z*]\d+(?:[A-Z*]|del)?)+$",
    re.IGNORECASE,
)


def construct_group(name: str) -> str:
    value = name.strip()
    value = MUTATION_SUFFIX.sub("", value)
    value = re.sub(r"_(?:PG|hp)(?:_.*)?$", "", value, flags=re.IGNORECASE)
    return value.removesuffix(".pdb")


def fold_for(group: str) -> int:
    digest = hashlib.sha256(f"bioeval-protein-v1:{group}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 5


def main() -> int:
    groups: set[str] = set()
    for path in sorted(SOURCE.glob("NGS_count_lib*.csv")):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader)
            for row in reader:
                if row:
                    groups.add(construct_group(row[0]))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["construct_group", "fold"])
        writer.writerows((group, fold_for(group)) for group in sorted(groups))
    print(f"Wrote {len(groups)} construct-family folds.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
