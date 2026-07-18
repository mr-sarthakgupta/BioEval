"""Shared deterministic IDR holdout helpers."""

from __future__ import annotations

import hashlib


def is_test_pair(assay: str, pair: str) -> bool:
    digest = hashlib.sha256(f"bioeval-idr-v1:{assay}:{pair}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 5 == 0


def pair_is_held_out(
    row: dict[str, object],
    held_out_pairs: set[str],
) -> bool:
    normalized = {pair.casefold().replace(" ", "") for pair in held_out_pairs}
    if row.get("pair") is not None:
        candidate = str(row["pair"]).casefold().replace(" ", "")
        if candidate in normalized:
            return True
    for left, right in (
        ("IDR_A", "IDR_B"),
        ("IDR1", "IDR2"),
        ("Protein_A", "Protein_B"),
    ):
        if row.get(left) is None or row.get(right) is None:
            continue
        first = str(row[left]).strip()
        second = str(row[right]).strip()
        candidates = {
            f"{first}-{second}".casefold().replace(" ", ""),
            f"{second}-{first}".casefold().replace(" ", ""),
        }
        if candidates & normalized:
            return True
    return False
