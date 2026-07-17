#!/usr/bin/env python3
"""Build a pair-grouped IDR perturbation prediction holdout."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41589-026-02251-9_idr-condensate-serine-charge"
SOURCE = PROBLEM / "evaluator" / "holdout_source"
TRAIN = PROBLEM / "curated" / "perturbation_training.csv"
TEST_ROWS = PROBLEM / "curated" / "perturbation_test_rows.csv"
TEST_LABELS = PROBLEM / "evaluator" / "perturbation_test_labels.csv"


def is_test_pair(assay: str, pair: str) -> bool:
    digest = hashlib.sha256(f"bioeval-idr-v1:{assay}:{pair}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 5 == 0


def main() -> int:
    train_rows: list[list[str]] = []
    test_rows: list[list[str]] = []
    for path in sorted(SOURCE.glob("*.csv")):
        assay = path.stem
        counts: dict[tuple[str, str], int] = {}
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = (row["pair"], row["Group"])
                replicate = counts.get(key, 0) + 1
                counts[key] = replicate
                output = [
                    assay,
                    row["pair"],
                    row["Group"],
                    str(replicate),
                    row["Pearson_r"],
                ]
                (test_rows if is_test_pair(assay, row["pair"]) else train_rows).append(output)

    TRAIN.parent.mkdir(parents=True, exist_ok=True)
    TEST_LABELS.parent.mkdir(parents=True, exist_ok=True)
    header = ["assay", "pair", "group", "replicate", "observed_pearson_r"]
    with TRAIN.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(train_rows)
    with TEST_ROWS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header[:-1])
        writer.writerows(row[:-1] for row in test_rows)
    with TEST_LABELS.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(test_rows)
    print(f"Wrote {len(train_rows)} training and {len(test_rows)} hidden rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
