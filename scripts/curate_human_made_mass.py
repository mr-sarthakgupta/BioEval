#!/usr/bin/env python3
"""Build a bounded, pre-2016 accounting bundle from staged audit tables."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41586-020-3010-5_human-made-mass"
SOURCE = PROBLEM / "evaluator" / "host-audit"
DESTINATION = PROBLEM / "curated"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    material_source = SOURCE / "annual_material_stocks_1900_2015.csv"
    biomass_source = SOURCE / "historical_biomass_estimates.csv"
    dictionary_source = SOURCE / "field_dictionary.csv"

    with material_source.open(newline="", encoding="utf-8") as handle:
        material_rows = list(csv.DictReader(handle))
        material_fields = list(material_rows[0])
    if [int(row["year"]) for row in material_rows] != list(range(1900, 2016)):
        raise RuntimeError("Material observations must cover 1900 through 2015.")
    material_output = DESTINATION / material_source.name
    with material_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=material_fields)
        writer.writeheader()
        writer.writerows(material_rows)

    with biomass_source.open(newline="", encoding="utf-8") as handle:
        biomass_rows = [
            row
            for row in csv.DictReader(handle)
            if int(row["observation_year"]) <= 2015
        ]
    biomass_output = DESTINATION / "historical_biomass_estimates_pre2016.csv"
    with biomass_output.open("w", newline="", encoding="utf-8") as handle:
        fields = ["source_group", "observation_year", "biomass_gt_carbon"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(biomass_rows)

    dictionary_output = DESTINATION / dictionary_source.name
    dictionary_output.write_bytes(dictionary_source.read_bytes())
    constants_output = DESTINATION / "accounting_constants.csv"
    with constants_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["parameter", "value", "unit"])
        writer.writerows(
            [
                ("observation_cutoff_year", "2015", "year"),
                ("carbon_to_dry_mass_min", "1.8", "dimensionless"),
                ("carbon_to_dry_mass_max", "2.2", "dimensionless"),
                ("anchor_years", "1900;1950;1980;2000;2010;2015", "year"),
            ]
        )

    outputs = [
        material_output,
        biomass_output,
        dictionary_output,
        constants_output,
    ]
    manifest = {
        "curation": (
            "bounded observation-only accounting bundle; post-2015 observations, "
            "projections, fitted trajectories, and crossing calculations excluded"
        ),
        "outputs": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in outputs
        ],
    }
    (DESTINATION / "input_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(outputs)} bounded accounting inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
