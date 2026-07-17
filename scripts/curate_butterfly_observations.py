#!/usr/bin/env python3
"""Convert selected butterfly observation data frames to neutral CSV tables."""

from __future__ import annotations

from pathlib import Path

import pyreadr


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41467-026-73635-7_butterfly-longevity-pollen-feeding"
SOURCE = PROBLEM / "data" / "figshare" / "31081597"
DESTINATION = PROBLEM / "curated" / "observations"
FILES = {
    "table_1_data.rds": "species_max_lifespan.csv",
    "totalcogsurv.RDS": "five_species_survival.csv",
    "longsurv.rds": "diet_survival.csv",
    "locomotordata.rds": "locomotor_activity.csv",
    "fullGSdata.rds": "grip_strength.csv",
    "fullweightdata2.rds": "body_weight.csv",
    "sightings.rds": "mark_recapture_sightings.csv",
    "IDdata.rds": "mark_recapture_individuals.csv",
}


def main() -> int:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    for source_name, destination_name in FILES.items():
        objects = pyreadr.read_r(SOURCE / source_name)
        if len(objects) != 1:
            raise ValueError(f"{source_name} did not contain exactly one data frame")
        frame = next(iter(objects.values()))
        frame.to_csv(DESTINATION / destination_name, index=False)
    print(f"Wrote {len(FILES)} neutral butterfly observation tables.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
