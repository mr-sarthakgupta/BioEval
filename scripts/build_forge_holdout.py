#!/usr/bin/env python3
"""Build the deterministic FORGE train/test response boundary."""

from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41467-026-73977-2_forge-cancer-drug-response"
SOURCE = PROBLEM / "data" / "figshare" / "31268542" / "Creammist_common_ic50.csv"
SPLIT = PROBLEM / "curated" / "cell_line_split.csv"
TRAIN = PROBLEM / "curated" / "drug_response_train.csv"
TEST_ROWS = PROBLEM / "curated" / "drug_response_test_rows.csv"
TEST_LABELS = PROBLEM / "evaluator" / "drug_response_test_labels.csv"


def main() -> int:
    with SPLIT.open(newline="") as handle:
        split = {row["cell_line_id"]: row["split"] for row in csv.DictReader(handle)}

    values: dict[tuple[str, str], list[float]] = defaultdict(list)
    with SOURCE.open(newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        selected = [(index, cell) for index, cell in enumerate(header[1:], 1) if cell in split]
        for row in reader:
            drug = row[0]
            for index, cell in selected:
                value = row[index].strip()
                if value:
                    values[(drug, cell)].append(float(value))

    train_rows: list[tuple[str, str, float]] = []
    test_rows: list[tuple[str, str, float]] = []
    for (drug, cell), observations in sorted(values.items()):
        row = (drug, cell, statistics.fmean(observations))
        (test_rows if split[cell] == "test" else train_rows).append(row)

    TRAIN.parent.mkdir(parents=True, exist_ok=True)
    TEST_LABELS.parent.mkdir(parents=True, exist_ok=True)
    with TRAIN.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["drug", "cell_line_id", "observed_ic50"])
        writer.writerows(train_rows)
    with TEST_ROWS.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["drug", "cell_line_id"])
        writer.writerows((drug, cell) for drug, cell, _ in test_rows)
    with TEST_LABELS.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["drug", "cell_line_id", "observed_ic50"])
        writer.writerows(test_rows)

    print(f"Wrote {len(train_rows)} training labels and {len(test_rows)} hidden test labels.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
