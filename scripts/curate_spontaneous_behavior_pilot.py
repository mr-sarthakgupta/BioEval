#!/usr/bin/env python3
"""Create a neutral, bounded event pilot from the selectively extracted parquet."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from pathlib import Path

import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41586-022-05611-2_spontaneous-behavior"
SOURCE = PROBLEM / "data" / "selective" / "3s-pulsed-stim-dataframe.parquet"
OUTPUT = PROBLEM / "curated" / "behavior_events_pilot.csv.gz"
COLUMNS = (
    "session_key",
    "animal_key",
    "module_key",
    "t_sec",
    "velocity_2d_mm",
    "photometry_z",
    "stim_state",
)


def opaque(prefix: str, value: object) -> str:
    digest = hashlib.sha256(
        f"bioeval-spontaneous-v1:{value}".encode("utf-8")
    ).hexdigest()[:12]
    return f"{prefix}_{digest}"


def main() -> int:
    table = pq.read_table(
        SOURCE,
        columns=[
            "uuid",
            "mouse_id",
            "predicted_syllable",
            "timestamp",
            "velocity_2d_mm",
            "dlight_reref_zscore",
            "feedback_status",
        ],
    )
    data = table.to_pydict()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with gzip.open(OUTPUT, "wt", newline="", encoding="utf-8") as raw:
        writer = csv.DictWriter(raw, fieldnames=COLUMNS)
        writer.writeheader()
        for index in range(table.num_rows):
            stim = int(data["feedback_status"][index])
            # Retain every intervention frame plus a deterministic 10% background sample.
            if stim == 0 and index % 10:
                continue
            numeric = [
                data["timestamp"][index],
                data["velocity_2d_mm"][index],
                data["dlight_reref_zscore"][index],
            ]
            if any(value is None or not math.isfinite(float(value)) for value in numeric):
                continue
            writer.writerow(
                {
                    "session_key": opaque("session", data["uuid"][index]),
                    "animal_key": opaque("animal", data["mouse_id"][index]),
                    "module_key": opaque("module", data["predicted_syllable"][index]),
                    "t_sec": f"{float(data['timestamp'][index]):.6f}",
                    "velocity_2d_mm": f"{float(data['velocity_2d_mm'][index]):.6f}",
                    "photometry_z": f"{float(data['dlight_reref_zscore'][index]):.8f}",
                    "stim_state": stim,
                }
            )
            rows += 1
    manifest = {
        "source_member": "dlight_raw_data/3s-pulsed-stim-dataframe.parquet",
        "source_rows": table.num_rows,
        "curated_rows": rows,
        "selection": "all nonzero feedback_status rows plus rows with source index modulo 10 equal to zero",
        "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
    }
    (OUTPUT.parent / "pilot_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {rows} neutral behavior events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
