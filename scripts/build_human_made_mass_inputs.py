#!/usr/bin/env python3
"""Build neutral input-only tables for the historical material-stock candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

try:
    import openpyxl
except ImportError as exc:  # pragma: no cover - dependency error is user-facing
    raise SystemExit("Install openpyxl to curate the source workbooks.") from exc


SOURCE_COMMIT = "5a0170a51d164c1cc98b232452e86feb1e4ee334"
MATERIAL_PATH = Path("data/anthropogenic_mass_2015.xlsx")
BIOMASS_PATH = Path("biomass_calculation/bm_est.xlsx")
MATERIAL_COLUMNS = (
    "year",
    "concrete_tt",
    "aggregate_tt",
    "brick_tt",
    "asphalt_tt",
    "metal_tt",
    "other_material_tt",
    "waste_tt",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sheet_rows(path: Path) -> list[tuple[object, ...]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return list(workbook.active.iter_rows(values_only=True))


def build(source: Path, output: Path) -> None:
    material_source = source / MATERIAL_PATH
    biomass_source = source / BIOMASS_PATH
    for path in (material_source, biomass_source):
        if not path.is_file():
            raise SystemExit(f"Missing required source workbook: {path}")

    output.mkdir(parents=True, exist_ok=True)
    material_rows = sheet_rows(material_source)
    if len(material_rows) != 117 or material_rows[0][0] != "Year":
        raise SystemExit("Unexpected material-stock workbook schema or row count.")

    material_output = output / "annual_material_stocks_1900_2015.csv"
    with material_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(MATERIAL_COLUMNS)
        years: list[int] = []
        for row in material_rows[1:]:
            year = int(row[0])
            values = [float(value) for value in row[1:8]]
            years.append(year)
            writer.writerow([year, *(f"{value:.12g}" for value in values)])
    if years != list(range(1900, 2016)):
        raise SystemExit("Material-stock years must be exactly 1900 through 2015.")

    biomass_rows = sheet_rows(biomass_source)
    if biomass_rows[0][:3] != ("data source", "year", "biomass [GtC]"):
        raise SystemExit("Unexpected biomass-estimate workbook schema.")
    biomass_output = output / "historical_biomass_estimates.csv"
    with biomass_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("source_group", "observation_year", "biomass_gt_carbon"))
        count = 0
        for row in biomass_rows[1:]:
            if row[0] is None or row[1] is None or row[2] is None:
                continue
            writer.writerow((str(row[0]).strip(), int(row[1]), f"{float(row[2]):.12g}"))
            count += 1
    if count < 10:
        raise SystemExit("Too few historical biomass estimates were recovered.")

    dictionary_output = output / "field_dictionary.csv"
    dictionary_rows = [
        ("year", "calendar year at end of annual accounting interval", "year"),
        ("concrete_tt", "global in-use stock assigned to concrete", "teratonnes"),
        ("aggregate_tt", "global in-use stock assigned to construction aggregates", "teratonnes"),
        ("brick_tt", "global in-use stock assigned to bricks", "teratonnes"),
        ("asphalt_tt", "global in-use stock assigned to asphalt", "teratonnes"),
        ("metal_tt", "global in-use stock assigned to metals", "teratonnes"),
        ("other_material_tt", "global in-use stock assigned to other materials", "teratonnes"),
        ("waste_tt", "separately accounted discarded material stock", "teratonnes"),
        ("source_group", "citation-level grouping retained for source-aware analysis", "category"),
        ("observation_year", "calendar year represented by a biomass estimate", "year"),
        ("biomass_gt_carbon", "global living biomass expressed as carbon mass", "gigatonnes carbon"),
    ]
    with dictionary_output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("field", "description", "unit"))
        writer.writerows(dictionary_rows)

    manifest = {
        "source_commit": SOURCE_COMMIT,
        "source_commit_date": "2020-09-18T15:35:37+03:00",
        "curation": "input-only workbook conversion; no post-2015 projection or fitted target trajectory",
        "sources": [
            {
                "path": str(MATERIAL_PATH),
                "bytes": material_source.stat().st_size,
                "sha256": sha256(material_source),
            },
            {
                "path": str(BIOMASS_PATH),
                "bytes": biomass_source.stat().st_size,
                "sha256": sha256(biomass_source),
            },
        ],
        "outputs": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in (material_output, biomass_output, dictionary_output)
        ],
    }
    (output / "source_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_checkout", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            Path(__file__).resolve().parents[1]
            / "problems_imcomplete"
            / "s41586-020-3010-5_human-made-mass"
            / "evaluator"
            / "host-audit"
        ),
    )
    args = parser.parse_args()
    build(args.source_checkout.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
