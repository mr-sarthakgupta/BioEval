#!/usr/bin/env python3
"""Stream a neutral, resource-bounded count-matrix pilot from the atlas archive."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path


PROBLEM_ID = "s41586-019-0933-9_mouse-gastrulation"
CELL_LIMIT = 2048
GENE_LIMIT = 5000
MIN_GENE_CELL_FRACTION = 0.01
NUMERIC_STAGE_RE = re.compile(r"^E(\d+(?:\.\d+)?)$")


def digest(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def opaque_id(kind: str, source: str) -> str:
    return f"{kind}_{digest(f'bioeval-gastrulation-{kind}-v2:{source}')[:12]}"


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def select_cells(meta_path: Path) -> list[tuple[int, dict[str, str]]]:
    with meta_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    by_stage: dict[str, list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for column_index, row in enumerate(rows, start=1):
        by_stage[row["stage"]].append((column_index, row))
    stages = sorted(by_stage)
    base, remainder = divmod(CELL_LIMIT, len(stages))
    selected: list[tuple[int, dict[str, str]]] = []
    for stage_index, stage in enumerate(stages):
        quota = base + (stage_index < remainder)
        ranked = sorted(
            by_stage[stage],
            key=lambda item: digest(f"bioeval-gastrulation-cell-v1:{item[1]['cell']}"),
        )
        selected.extend(ranked[:quota])
    return sorted(selected)


def select_genes(genes_path: Path) -> list[tuple[int, tuple[str, str]]]:
    rows: list[tuple[int, tuple[str, str]]] = []
    with genes_path.open(encoding="utf-8") as handle:
        for row_index, line in enumerate(handle, start=1):
            parts = line.rstrip("\n").split("\t")
            rows.append((row_index, (parts[0], parts[1] if len(parts) > 1 else "")))
    return sorted(
        sorted(
            rows,
            key=lambda item: digest(f"bioeval-gastrulation-gene-v1:{item[1][0]}"),
        )[:GENE_LIMIT]
    )


def heldout_samples(cells: list[tuple[int, dict[str, str]]]) -> set[str]:
    samples_by_stage: dict[str, set[str]] = defaultdict(set)
    for _, row in cells:
        if NUMERIC_STAGE_RE.fullmatch(row["stage"]):
            samples_by_stage[row["stage"]].add(row["sample"])
    return {
        min(
            samples,
            key=lambda sample: digest(
                f"bioeval-gastrulation-holdout-v1:{stage}:{sample}"
            ),
        )
        for stage, samples in samples_by_stage.items()
    }


def frozen_expression_baseline(
    entries_path: Path,
    retained_map: dict[int, int],
    cells: list[tuple[int, dict[str, str]]],
    heldout: set[str],
    *,
    neighbors: int = 5,
) -> dict[str, float]:
    samples = sorted({row["sample"] for _, row in cells})
    vectors = {sample: [0.0] * len(retained_map) for sample in samples}
    with entries_path.open(encoding="utf-8") as entries:
        for line in entries:
            source_gene, cell_index, count = line.split()
            gene_index = retained_map.get(int(source_gene))
            if gene_index is None:
                continue
            sample = cells[int(cell_index) - 1][1]["sample"]
            vectors[sample][gene_index - 1] += float(count)

    normalized: dict[str, list[float]] = {}
    for sample, values in vectors.items():
        total = sum(values)
        if total <= 0:
            raise SystemExit(f"Sample {sample} has no retained expression counts.")
        normalized[sample] = [math.log1p(value * 10_000 / total) for value in values]

    training: list[tuple[str, float]] = []
    for sample in samples:
        if sample in heldout:
            continue
        stages = {
            float(match.group(1))
            for _, row in cells
            if row["sample"] == sample
            if (match := NUMERIC_STAGE_RE.fullmatch(row["stage"]))
        }
        if len(stages) == 1:
            training.append((sample, stages.pop()))

    predictions: dict[str, float] = {}
    norms = {
        sample: math.sqrt(sum(value * value for value in vector))
        for sample, vector in normalized.items()
    }
    for sample in heldout:
        target = normalized[sample]
        similarities: list[tuple[float, float]] = []
        for training_sample, stage in training:
            similarity = sum(
                left * right
                for left, right in zip(target, normalized[training_sample])
            ) / max(norms[sample] * norms[training_sample], 1e-12)
            similarities.append((similarity, stage))
        nearest = sorted(similarities, reverse=True)[:neighbors]
        weights = [max(similarity, 1e-6) for similarity, _ in nearest]
        predictions[sample] = sum(
            weight * stage for weight, (_, stage) in zip(weights, nearest)
        ) / sum(weights)
    return predictions


def build(archive: Path, meta_path: Path, genes_path: Path, problem_root: Path) -> None:
    curated = problem_root / "curated" / "sanitized-counts"
    evaluator = problem_root / "evaluator"
    curated.mkdir(parents=True, exist_ok=True)
    evaluator.mkdir(parents=True, exist_ok=True)

    cells = select_cells(meta_path)
    genes = select_genes(genes_path)
    cell_map = {old: new for new, (old, _) in enumerate(cells, start=1)}
    gene_map = {old: new for new, (old, _) in enumerate(genes, start=1)}
    heldout = heldout_samples(cells)

    hidden_cells = evaluator / "cell_source_mapping.csv"
    with hidden_cells.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("source_column", "opaque_cell_id", "source_cell_id"))
        for new, (old, row) in enumerate(cells, start=1):
            writer.writerow((old, f"cell_{new:05d}", row["cell"]))
    sample_mapping = evaluator / "sample_batch_source_mapping.csv"
    with sample_mapping.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("opaque_sample_id", "opaque_batch_id", "source_sample", "source_batch")
        )
        seen: set[tuple[str, str]] = set()
        for _, row in cells:
            key = (row["sample"], row["sequencing.batch"])
            if key in seen:
                continue
            seen.add(key)
            writer.writerow(
                (
                    opaque_id("sample", row["sample"]),
                    opaque_id("batch", row["sequencing.batch"]),
                    row["sample"],
                    row["sequencing.batch"],
                )
            )

    cells_path = curated / "cells.tsv"
    holdout_path = evaluator / "trajectory_holdout_labels.csv"
    holdout_rows: list[tuple[str, str, float, str]] = []
    with cells_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            (
                "cell_id",
                "sample_id",
                "stage",
                "sequencing_batch",
                "theiler_stage",
                "evaluation_split",
            )
        )
        for new, (_, row) in enumerate(cells, start=1):
            cell_id = f"cell_{new:05d}"
            sample_id = opaque_id("sample", row["sample"])
            is_holdout = row["sample"] in heldout
            match = NUMERIC_STAGE_RE.fullmatch(row["stage"])
            if is_holdout and match:
                holdout_rows.append(
                    (cell_id, sample_id, float(match.group(1)), row["sample"])
                )
            writer.writerow(
                (
                    cell_id,
                    sample_id,
                    "" if is_holdout else row["stage"],
                    "" if is_holdout else opaque_id("batch", row["sequencing.batch"]),
                    "" if is_holdout else row["theiler"],
                    "holdout" if is_holdout else "training",
                )
            )
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp)
        cell_map_path = temp / "cell_map.tsv"
        gene_map_path = temp / "gene_map.tsv"
        entries_path = temp / "entries.mtx"
        count_path = temp / "count.txt"
        cell_map_path.write_text(
            "".join(f"{old}\t{new}\n" for old, new in cell_map.items()),
            encoding="utf-8",
        )
        gene_map_path.write_text(
            "".join(f"{old}\t{new}\n" for old, new in gene_map.items()),
            encoding="utf-8",
        )
        tar = subprocess.Popen(
            ["tar", "-xOzf", str(archive), "atlas/raw_counts.mtx"],
            stdout=subprocess.PIPE,
        )
        assert tar.stdout is not None
        awk_program = (
            'BEGIN {FS=OFS=" "} '
            'FILENAME==ARGV[1] {g[$1]=$2; next} '
            'FILENAME==ARGV[2] {c[$1]=$2; next} '
            'FNR<=2 {next} '
            '($1 in g) && ($2 in c) {print g[$1], c[$2], $3; n++} '
            f'END {{print n > "{count_path}"}}'
        )
        with entries_path.open("w", encoding="utf-8") as entries:
            awk = subprocess.run(
                [
                    "awk",
                    awk_program,
                    str(gene_map_path),
                    str(cell_map_path),
                    "-",
                ],
                stdin=tar.stdout,
                stdout=entries,
                check=True,
            )
        del awk
        if tar.wait() != 0:
            raise SystemExit("Failed to stream raw count matrix from archive.")
        del count_path
        detections: dict[int, int] = defaultdict(int)
        with entries_path.open(encoding="utf-8") as entries:
            for line in entries:
                gene_index = int(line.split(" ", 1)[0])
                detections[gene_index] += 1
        minimum_cells = math.ceil(len(cells) * MIN_GENE_CELL_FRACTION)
        retained = [
            gene_index
            for gene_index in range(1, len(genes) + 1)
            if detections[gene_index] >= minimum_cells
        ]
        retained_map = {
            old_index: new_index
            for new_index, old_index in enumerate(retained, start=1)
        }
        nonzero = sum(detections[index] for index in retained)
        matrix_path = curated / "counts.mtx.gz"
        with gzip.open(matrix_path, "wt", encoding="utf-8", newline="\n") as output:
            output.write("%%MatrixMarket matrix coordinate integer general\n")
            output.write(f"{len(retained)} {len(cells)} {nonzero}\n")
            with entries_path.open(encoding="utf-8") as entries:
                for line in entries:
                    gene_index, rest = line.split(" ", 1)
                    remapped = retained_map.get(int(gene_index))
                    if remapped is not None:
                        output.write(f"{remapped} {rest}")
        baseline_predictions = frozen_expression_baseline(
            entries_path, retained_map, cells, heldout
        )

    with holdout_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("cell_id", "heldout_group", "observed_time", "baseline_predicted_time")
        )
        writer.writerows(
            (
                cell_id,
                heldout_group,
                observed_time,
                f"{baseline_predictions[source_sample]:.12g}",
            )
            for cell_id, heldout_group, observed_time, source_sample in holdout_rows
        )

    genes_out = curated / "genes.tsv"
    with genes_out.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("gene_id", "gene_symbol"))
        for old_index in retained:
            _, (gene_id, symbol) = genes[old_index - 1]
            writer.writerow((gene_id, symbol))

    manifest = {
        "schema_version": "1.0",
        "selection": {
            "cells": CELL_LIMIT,
            "genes": len(retained),
            "cell_rule": "stage-balanced lowest SHA-256 bioeval-gastrulation-cell-v1",
            "gene_rule": "lowest SHA-256 bioeval-gastrulation-gene-v1",
            "gene_expression_filter": (
                f"detected in at least {minimum_cells} pilot cells "
                f"({MIN_GENE_CELL_FRACTION:.0%})"
            ),
            "holdout_rule": (
                "one deterministic complete sample per numeric developmental stage; "
                "source sample ordinality, batch, stage, and Theiler labels removed "
                "from holdout metadata"
            ),
            "metadata_blinding": "non-ordinal SHA-256-derived sample and batch IDs",
            "frozen_baseline": (
                "five-nearest training-sample pseudobulks after library-size "
                "normalization and log1p"
            ),
            "holdout_cells": len(holdout_rows),
        },
        "matrix_nonzero": nonzero,
        "source_archive": {
            "bytes": archive.stat().st_size,
            "sha256": sha256(archive),
        },
        "grantable_outputs": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in (matrix_path, genes_out, cells_path)
        ],
        "hidden_evaluator": {
            "path": holdout_path.name,
            "rows": len(holdout_rows),
            "sha256": sha256(holdout_path),
        },
    }
    (problem_root / "curated" / "sanitized_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[1]
    problem_root = root / "problems_imcomplete" / PROBLEM_ID
    parser.add_argument(
        "--archive",
        type=Path,
        default=problem_root / "data" / "biostudies" / "atlas_data.tar.gz",
    )
    parser.add_argument("--meta", type=Path, default=Path("/tmp/gastrulation_meta.csv"))
    parser.add_argument("--genes", type=Path, default=Path("/tmp/gastrulation_genes.tsv"))
    args = parser.parse_args()
    build(
        args.archive.resolve(),
        args.meta.resolve(),
        args.genes.resolve(),
        problem_root.resolve(),
    )


if __name__ == "__main__":
    main()
