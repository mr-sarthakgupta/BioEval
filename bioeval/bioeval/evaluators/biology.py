from __future__ import annotations

import array
import csv
import gzip
import hashlib
import json
import math
import re
import struct
import sys
from collections import defaultdict
from pathlib import Path

from bioeval.problems import resolve_problem_root
from bioeval.evaluators.registry import (
    EvaluatorOutput,
    _contract_evaluator,
    _safe_artifact,
    register_evaluator,
)

GASTRULATION_ID = "s41586-019-0933-9_mouse-gastrulation"
RNA_HYDRATION_ID = "s41586-025-08855-w_rna-hydration"
RIVER_METHANE_ID = "s41586-023-06344-6_global-river-methane"
HUMAN_MASS_ID = "s41586-020-3010-5_human-made-mass"
CHROMATIN_ID = "nature09906_chromatin-state-dynamics"
F1_ATPASE_ID = "s41467-026-73844-0_f1-atpase-markov-model"
PROTEIN_RESISTANCE_ID = "s41586-023-06328-6_protein-protease-resistance"
SPONTANEOUS_BEHAVIOR_ID = "s41586-022-05611-2_spontaneous-behavior"
TRACEBIND_ID = "s41467-026-73164-3_tracebind-atac-footprinting"
MITO_NUCLEAR_PORE_ID = "s41586-026-10588-3_mitochondria-nuclear-pore-interaction"


def _problem_root(problem_id: str) -> Path:
    root = resolve_problem_root(problem_id)
    if root is None:
        raise FileNotFoundError(f"Problem directory is missing: {problem_id}")
    return root


def _declared_artifacts(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> tuple[Path | None, dict[str, Path], list[str]]:
    if not manifest_verified or manifest_path is None:
        return None, {}, ["Required analysis manifest was missing or invalid."]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, {}, ["Required analysis manifest could not be read."]
    root = (artifact_root or manifest_path.parent).resolve()
    declared: dict[str, Path] = {}
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            continue
        path = _safe_artifact(root, item["path"])
        if path is not None:
            declared[item["path"]] = path
    return root, declared, []


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _combine_contract(
    problem_id: str,
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    return _contract_evaluator(problem_id)(
        manifest_path,
        artifact_root,
        manifest_verified,
    )


def _linear_quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index + 1
        while end < len(order) and values[order[end]] == values[order[index]]:
            end += 1
        rank = (index + end - 1) / 2 + 1
        for position in order[index:end]:
            ranks[position] = rank
        index = end
    return ranks


def _spearman(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Spearman correlation requires paired values.")
    x = _average_ranks(left)
    y = _average_ranks(right)
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    denominator = math.sqrt(
        sum((a - x_mean) ** 2 for a in x)
        * sum((b - y_mean) ** 2 for b in y)
    )
    return numerator / denominator if denominator else 0.0


def _river_methane_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        RIVER_METHANE_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    summary_path = declared.get("observation_summary.csv")
    if summary_path is None:
        failures.append("River observation summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)

    root = _problem_root(RIVER_METHANE_ID) / "data" / "primary-observations"
    definitions = {
        "concentration": (
            root / "GRiMe_concentrations_v2.csv",
            "CH4mean",
            lambda row: True,
        ),
        "measured_diffusive_flux": (
            root / "GRiMe_fluxes_v2.csv",
            "Diffusive_CH4_Flux_Mean",
            lambda row: row.get("Diff_Method", "") not in {"", "NA", "conc+k"},
        ),
    }
    try:
        submitted_rows = _read_csv(summary_path)
        submitted = {row["dataset"]: row for row in submitted_rows}
        if len(submitted_rows) != len(definitions) or len(submitted) != len(definitions):
            failures.append(
                "River observation summary must contain exactly one row per dataset."
            )
        expected: dict[str, dict[str, float | int]] = {}
        for name, (path, value_column, include) in definitions.items():
            values: list[float] = []
            sources: set[str] = set()
            for row in _read_csv(path):
                if not include(row):
                    continue
                try:
                    value = float(row[value_column])
                except (KeyError, TypeError, ValueError):
                    continue
                if math.isfinite(value) and value > 0:
                    values.append(value)
                    sources.add(row["Source_ID"])
            expected[name] = {
                "positive_rows": len(values),
                "source_count": len(sources),
                "q10": _linear_quantile(values, 0.10),
                "median": _linear_quantile(values, 0.50),
                "q90": _linear_quantile(values, 0.90),
            }
    except (OSError, csv.Error, KeyError):
        failures.append("Could not read river methane inputs or submitted summary.")
        return EvaluatorOutput(contract.summary, failures)

    for name, reference in expected.items():
        row = submitted.get(name)
        if row is None:
            failures.append(f"Missing river summary row for {name}.")
            continue
        for column in ("positive_rows", "source_count"):
            try:
                actual = int(row[column])
            except (KeyError, TypeError, ValueError):
                failures.append(f"{name}.{column} is not an integer.")
                continue
            if actual != reference[column]:
                failures.append(f"{name}.{column} does not match the frozen observations.")
        for column in ("q10", "median", "q90"):
            try:
                actual = float(row[column])
            except (KeyError, TypeError, ValueError):
                failures.append(f"{name}.{column} is not numeric.")
                continue
            target = float(reference[column])
            if not math.isfinite(actual) or not math.isclose(
                actual, target, rel_tol=1e-5, abs_tol=1e-8
            ):
                failures.append(f"{name}.{column} does not match the frozen observations.")

    return EvaluatorOutput(
        f"{contract.summary}; verified_observation_summaries="
        f"{len(definitions) - sum('Missing river summary row' in item for item in failures)}",
        list(dict.fromkeys(failures)),
    )


def _gastrulation_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        GASTRULATION_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *failures]
    prediction_path = declared.get("trajectory_holdout.csv")
    labels_path = (
        _problem_root(GASTRULATION_ID) / "evaluator" / "trajectory_holdout_labels.csv"
    )
    if prediction_path is None or not labels_path.is_file():
        failures.append("Gastrulation scientific evaluator inputs are incomplete.")
        return EvaluatorOutput(contract.summary, failures)

    try:
        labels = {row["cell_id"]: row for row in _read_csv(labels_path)}
        rows = _read_csv(prediction_path)
    except (OSError, csv.Error, KeyError):
        failures.append("Could not read gastrulation holdout artifacts or hidden labels.")
        return EvaluatorOutput(contract.summary, failures)

    predictions: dict[str, float] = {}
    duplicates = 0
    unknown = 0
    for row in rows:
        cell_id = row.get("cell_id", "")
        if cell_id in predictions:
            duplicates += 1
            continue
        if cell_id not in labels:
            unknown += 1
            continue
        try:
            predicted = float(row["predicted_time"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(predicted):
            continue
        predictions[cell_id] = predicted
    coverage = len(predictions) / max(1, len(labels))
    if duplicates:
        failures.append(f"trajectory_holdout.csv has {duplicates} duplicate cell IDs.")
    if unknown:
        failures.append(f"trajectory_holdout.csv has {unknown} unknown cell IDs.")
    if coverage < 0.95:
        failures.append(f"Hidden holdout coverage is {coverage:.3f}; requires at least 0.95.")

    scored = [
        (predicted, float(labels[cell_id]["observed_time"]))
        for cell_id, predicted in predictions.items()
    ]
    rmse = math.inf
    baseline_rmse = math.inf
    if scored:
        rmse = math.sqrt(sum((p - y) ** 2 for p, y in scored) / len(scored))
        baseline_rmse = math.sqrt(
            sum(
                (
                    float(labels[cell_id]["baseline_predicted_time"])
                    - float(labels[cell_id]["observed_time"])
                )
                ** 2
                for cell_id in predictions
            )
            / len(predictions)
        )
        if rmse > baseline_rmse * 1.05:
            failures.append(
                f"Holdout RMSE {rmse:.4f} is worse than the frozen expression "
                f"baseline {baseline_rmse:.4f} plus 5% tolerance."
            )

    return EvaluatorOutput(
        f"{contract.summary}; hidden_holdout={len(predictions)}/{len(labels)}; "
        f"RMSE={rmse:.6g}; baseline_RMSE={baseline_rmse:.6g}",
        list(dict.fromkeys(failures)),
    )


class _MrcMap:
    def __init__(self, path: Path) -> None:
        with gzip.open(path, "rb") as handle:
            header = handle.read(1024)
            if len(header) != 1024:
                raise ValueError("truncated MRC header")
            self.nx, self.ny, self.nz, mode = struct.unpack_from("<4i", header, 0)
            self.starts = struct.unpack_from("<3i", header, 16)
            mx, my, mz = struct.unpack_from("<3i", header, 28)
            cell = struct.unpack_from("<3f", header, 40)
            self.axis_order = struct.unpack_from("<3i", header, 64)
            nsymbt = struct.unpack_from("<i", header, 92)[0]
            self.origin = struct.unpack_from("<3f", header, 196)
            if mode != 2 or min(self.nx, self.ny, self.nz, mx, my, mz) <= 0:
                raise ValueError("unsupported MRC geometry")
            if sorted(self.axis_order) != [1, 2, 3]:
                raise ValueError("invalid MRC axis order")
            self.voxel = (cell[0] / mx, cell[1] / my, cell[2] / mz)
            if nsymbt:
                handle.read(nsymbt)
            payload = handle.read()
        expected = self.nx * self.ny * self.nz
        self.values = array.array("f")
        self.values.frombytes(payload)
        if sys.byteorder != "little":
            self.values.byteswap()
        if len(self.values) != expected:
            raise ValueError("MRC payload size does not match its header")

    def _fractional_indices(
        self, point: tuple[float, float, float]
    ) -> tuple[float, float, float]:
        physical_grid = [
            (point[index] - self.origin[index]) / self.voxel[index]
            for index in range(3)
        ]
        column = physical_grid[self.axis_order[0] - 1] - self.starts[0]
        row = physical_grid[self.axis_order[1] - 1] - self.starts[1]
        section = physical_grid[self.axis_order[2] - 1] - self.starts[2]
        return column, row, section

    def sample(self, point: tuple[float, float, float]) -> float:
        column, row, section = self._fractional_indices(point)
        if not (
            0 <= column < self.nx - 1
            and 0 <= row < self.ny - 1
            and 0 <= section < self.nz - 1
        ):
            raise ValueError("coordinate is outside the MRC grid")
        c0, r0, s0 = int(column), int(row), int(section)
        dc, dr, ds = column - c0, row - r0, section - s0

        def value(c: int, r: int, s: int) -> float:
            return float(self.values[(s * self.ny + r) * self.nx + c])

        result = 0.0
        for z_offset, z_weight in ((0, 1 - ds), (1, ds)):
            for y_offset, y_weight in ((0, 1 - dr), (1, dr)):
                for x_offset, x_weight in ((0, 1 - dc), (1, dc)):
                    result += (
                        value(c0 + x_offset, r0 + y_offset, s0 + z_offset)
                        * x_weight
                        * y_weight
                        * z_weight
                    )
        return result

    def peak_sigma(self, point: tuple[float, float, float]) -> float:
        center = self.sample(point)
        background: list[float] = []
        for dx in (-4.0, 0.0, 4.0):
            for dy in (-4.0, 0.0, 4.0):
                for dz in (-4.0, 0.0, 4.0):
                    radius = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if radius < 3.0 or radius > 7.0:
                        continue
                    try:
                        background.append(
                            self.sample(
                                (point[0] + dx, point[1] + dy, point[2] + dz)
                            )
                        )
                    except ValueError:
                        pass
        if len(background) < 12:
            raise ValueError("insufficient local background samples")
        mean = sum(background) / len(background)
        variance = sum((value - mean) ** 2 for value in background) / len(
            background
        )
        return (center - mean) / max(math.sqrt(variance), 0.05)


def _rna_hydration_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        RNA_HYDRATION_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *failures]
    calls_path = declared.get("hydration_calls.csv")
    parameters_path = declared.get("analysis_parameters.csv")
    problem_root = _problem_root(RNA_HYDRATION_ID)
    manifest_csv = problem_root / "curated" / "map_manifest.csv"
    if (
        calls_path is None
        or parameters_path is None
        or not manifest_csv.is_file()
    ):
        failures.append("RNA hydration scientific evaluator inputs are incomplete.")
        return EvaluatorOutput(contract.summary, failures)

    try:
        calls = _read_csv(calls_path)
        parameter_rows = _read_csv(parameters_path)
        map_rows = _read_csv(manifest_csv)
    except (OSError, csv.Error):
        failures.append("Could not read RNA hydration artifacts or map manifest.")
        return EvaluatorOutput(contract.summary, failures)

    parameters = {
        row.get("parameter", ""): row.get("value", "") for row in parameter_rows
    }
    expected_parameters = {
        "coordinate_frame": "map_angstrom",
        "minimum_peak_sigma": "3.0",
        "replication_radius_angstrom": "1.5",
    }
    for name, value in expected_parameters.items():
        if parameters.get(name) != value:
            failures.append(
                f"analysis_parameters.csv must declare {name}={value}."
            )
    parameter_hash = hashlib.sha256(parameters_path.read_bytes()).hexdigest()
    map_metadata = {
        (row["map_blind_id"], row["half_id"]): row for row in map_rows
    }
    map_cache: dict[tuple[str, str], _MrcMap] = {}

    def load_map(key: tuple[str, str]) -> _MrcMap:
        if key not in map_cache:
            row = map_metadata[key]
            map_path = problem_root / "data" / "half-maps" / row["filename"]
            if hashlib.sha256(map_path.read_bytes()).hexdigest() != row["sha256"]:
                raise ValueError("map hash mismatch")
            map_cache[key] = _MrcMap(map_path)
        return map_cache[key]

    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in calls:
        key = (row.get("map_blind_id", ""), row.get("site_id", ""))
        grouped[key].append(row)
        map_key = (row.get("map_blind_id", ""), row.get("half_id", ""))
        expected_map = map_metadata.get(map_key)
        if expected_map is None or row.get("input_sha256") != expected_map["sha256"]:
            failures.append("hydration_calls.csv contains an incorrect input SHA-256.")
        if row.get("parameter_sha256") != parameter_hash:
            failures.append(
                "hydration_calls.csv parameter SHA-256 does not match analysis_parameters.csv."
            )

    valid_points: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
    eligible = 0
    for (map_id, _), site_rows in grouped.items():
        halves = {row.get("half_id") for row in site_rows}
        if len(site_rows) != 2 or halves != {"1", "2"}:
            failures.append(
                "Each RNA site must have exactly one row for each of the two half-maps."
            )
            continue
        try:
            points = [
                (
                    float(row["x_angstrom"]),
                    float(row["y_angstrom"]),
                    float(row["z_angstrom"]),
                )
                for row in site_rows
            ]
        except (KeyError, TypeError, ValueError):
            continue
        if math.dist(points[0], points[1]) > 1.5:
            failures.append("A replicated hydration site differs by more than 1.5 Å.")
            continue
        point = tuple(sum(values) / len(values) for values in zip(*points))
        site_valid = True
        for row, row_point in zip(site_rows, points):
            try:
                recomputed = load_map((map_id, row["half_id"])).peak_sigma(row_point)
                submitted = float(row["peak_sigma"])
            except (KeyError, OSError, ValueError, struct.error):
                failures.append("Could not evaluate a submitted site against its half-map.")
                site_valid = False
                continue
            if recomputed < 3.0:
                failures.append(
                    f"Site {map_id}/{row.get('site_id', '')} is below the "
                    f"replicated density threshold in half {row['half_id']}."
                )
                site_valid = False
            if not math.isfinite(submitted) or abs(submitted - recomputed) > 1.0:
                failures.append(
                    "Submitted peak_sigma differs from the evaluator-recomputed density."
                )
                site_valid = False
        if site_valid:
            if any(
                math.dist(point, existing) <= 1.5
                for existing in valid_points[map_id]
            ):
                failures.append(
                    "Distinct RNA site IDs collapse onto the same spatial peak."
                )
                continue
            valid_points[map_id].append(point)
            eligible += 1

    if eligible < 10:
        failures.append("Fewer than 10 replicated density sites were submitted.")
    for map_id in ("map_a", "map_b"):
        if len(valid_points[map_id]) < 3:
            failures.append(
                f"Fewer than 3 replicated density sites passed for {map_id}."
            )
    cross_used: set[int] = set()
    cross_reconstruction = 0
    for point_a in valid_points["map_a"]:
        candidates = [
            (index, math.dist(point_a, point_b))
            for index, point_b in enumerate(valid_points["map_b"])
            if index not in cross_used
        ]
        if not candidates:
            continue
        index, distance = min(candidates, key=lambda item: item[1])
        if distance <= 1.5:
            cross_used.add(index)
            cross_reconstruction += 1
    if cross_reconstruction < 3:
        failures.append(
            "Fewer than 3 resolved sites replicate across the two reconstructions."
        )

    return EvaluatorOutput(
        f"{contract.summary}; replicated_submitted={eligible}; "
        f"density_valid={sum(map(len, valid_points.values()))}; "
        f"cross_reconstruction={cross_reconstruction}",
        list(dict.fromkeys(failures)),
    )


def _human_mass_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        HUMAN_MASS_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    material_path = declared.get("material_stock_summary.csv")
    biomass_path = declared.get("biomass_envelope.csv")
    if material_path is None or biomass_path is None:
        if material_path is None:
            failures.append("Material stock summary was not declared.")
        if biomass_path is None:
            failures.append("Biomass envelope was not declared.")
        return EvaluatorOutput(contract.summary, failures)

    root = _problem_root(HUMAN_MASS_ID) / "curated"
    anchors = {1900, 1950, 1980, 2000, 2010, 2015}
    expected_material: dict[tuple[str, int], float] = {}
    expected_biomass: dict[str, tuple[int, float, float, float]] = {}
    try:
        material_rows = _read_csv(root / "annual_material_stocks_1900_2015.csv")
        for row in material_rows:
            year = int(row["year"])
            if year not in anchors:
                continue
            in_use = sum(
                float(row[column])
                for column in (
                    "concrete_tt",
                    "aggregate_tt",
                    "brick_tt",
                    "asphalt_tt",
                    "metal_tt",
                    "other_material_tt",
                )
            )
            expected_material[("in_use_only", year)] = in_use
            expected_material[("in_use_plus_waste", year)] = (
                in_use + float(row["waste_tt"])
            )
        biomass_rows = _read_csv(root / "historical_biomass_estimates_pre2016.csv")
        for row in biomass_rows:
            if int(row["observation_year"]) != 2010:
                continue
            carbon = float(row["biomass_gt_carbon"])
            expected_biomass[row["source_group"]] = (
                2010,
                carbon,
                carbon * 1.8,
                carbon * 2.2,
            )
        submitted_material_rows = _read_csv(material_path)
        submitted_biomass_rows = _read_csv(biomass_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        failures.append(f"Could not recompute mass accounting inputs ({type(exc).__name__}).")
        return EvaluatorOutput(contract.summary, failures)

    submitted_material: dict[tuple[str, int], float] = {}
    for row in submitted_material_rows:
        try:
            key = (row["accounting_definition"], int(row["anchor_year"]))
            value = float(row["total_teratonnes"])
        except (ValueError, KeyError):
            failures.append("Material stock summary contains an invalid row.")
            continue
        if key in submitted_material:
            failures.append("Material stock summary contains duplicate keys.")
        submitted_material[key] = value
    if set(submitted_material) != set(expected_material):
        failures.append("Material stock summary does not contain the exact anchor grid.")
    for key, expected in expected_material.items():
        submitted = submitted_material.get(key)
        if submitted is None or not math.isclose(
            submitted, expected, rel_tol=1e-6, abs_tol=1e-9
        ):
            failures.append(
                f"Material stock total was not recomputed for {key[0]}/{key[1]}."
            )

    submitted_biomass: dict[str, tuple[int, float, float, float]] = {}
    for row in submitted_biomass_rows:
        try:
            key = row["source_group"]
            value = (
                int(row["observation_year"]),
                float(row["biomass_gt_carbon"]),
                float(row["biomass_dry_min_gt"]),
                float(row["biomass_dry_max_gt"]),
            )
        except (ValueError, KeyError):
            failures.append("Biomass envelope contains an invalid row.")
            continue
        if key in submitted_biomass:
            failures.append("Biomass envelope contains duplicate source groups.")
        submitted_biomass[key] = value
    if set(submitted_biomass) != set(expected_biomass):
        failures.append("Biomass envelope does not contain the exact 2010 source set.")
    for source, expected in expected_biomass.items():
        submitted = submitted_biomass.get(source)
        if submitted is None or submitted[0] != expected[0] or any(
            not math.isclose(observed, target, rel_tol=1e-6, abs_tol=1e-6)
            for observed, target in zip(submitted[1:], expected[1:])
        ):
            failures.append(
                f"Biomass dry-mass envelope was not recomputed for {source}."
            )

    return EvaluatorOutput(
        f"{contract.summary}; material_anchors={len(expected_material)}; "
        f"biomass_sources={len(expected_biomass)}",
        list(dict.fromkeys(failures)),
    )


def _chromatin_pilot_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        CHROMATIN_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    summary_path = declared.get("chromatin_bin_summary.csv")
    if summary_path is None:
        failures.append("Chromatin bin summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)

    root = _problem_root(CHROMATIN_ID)
    try:
        track_rows = _read_csv(root / "curated" / "pilot_track_map.csv")
        counts: dict[str, dict[tuple[str, int], int]] = {}
        totals: dict[str, int] = {}
        for track in track_rows:
            track_id = track["track_id"]
            path = (
                root
                / "data"
                / "pilot-h1-k562-chr21-chr22"
                / track["filename"]
            )
            track_counts: dict[tuple[str, int], int] = defaultdict(int)
            total = 0
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    fields = line.split("\t", 3)
                    if len(fields) < 3 or fields[0] not in {"chr21", "chr22"}:
                        continue
                    midpoint = (int(fields[1]) + int(fields[2])) // 2
                    track_counts[(fields[0], midpoint // 1_000_000 * 1_000_000)] += 1
                    total += 1
            counts[track_id] = track_counts
            totals[track_id] = total

        expected: dict[tuple[str, str, int, str], tuple[float, float, float]] = {}
        for cell_type in ("H1", "K562"):
            control_id = f"{cell_type}_WCE"
            for mark in ("H3K27me3", "H3K4me3"):
                mark_id = f"{cell_type}_{mark}"
                keys = set(counts[mark_id]) | set(counts[control_id])
                for chromosome, bin_start in keys:
                    mark_rpm = counts[mark_id].get((chromosome, bin_start), 0) * (
                        1_000_000 / totals[mark_id]
                    )
                    control_rpm = counts[control_id].get(
                        (chromosome, bin_start), 0
                    ) * (1_000_000 / totals[control_id])
                    enrichment = math.log2(
                        (mark_rpm + 1.0) / (control_rpm + 1.0)
                    )
                    expected[(cell_type, chromosome, bin_start, mark)] = (
                        mark_rpm,
                        control_rpm,
                        enrichment,
                    )
        submitted_rows = _read_csv(summary_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        failures.append(f"Could not recompute chromatin pilot ({type(exc).__name__}).")
        return EvaluatorOutput(contract.summary, failures)

    submitted: dict[tuple[str, str, int, str], tuple[float, float, float]] = {}
    for row in submitted_rows:
        try:
            key = (
                row["cell_type"],
                row["chromosome"],
                int(row["bin_start"]),
                row["mark"],
            )
            value = (
                float(row["mark_rpm"]),
                float(row["control_rpm"]),
                float(row["log2_enrichment"]),
            )
        except (ValueError, KeyError):
            failures.append("Chromatin bin summary contains an invalid row.")
            continue
        if key in submitted:
            failures.append("Chromatin bin summary contains duplicate keys.")
        submitted[key] = value
    if set(submitted) != set(expected):
        failures.append("Chromatin bin summary does not contain the exact pilot bin grid.")
    mismatches = 0
    for key, target in expected.items():
        observed = submitted.get(key)
        if observed is None or any(
            not math.isclose(value, reference, rel_tol=1e-5, abs_tol=1e-6)
            for value, reference in zip(observed, target)
        ):
            mismatches += 1
    if mismatches:
        failures.append(
            f"Chromatin bin metrics were not recomputed for {mismatches} bins."
        )
    return EvaluatorOutput(
        f"{contract.summary}; recomputed_bins={len(expected)}; mismatches={mismatches}",
        list(dict.fromkeys(failures)),
    )


def _f1_observation_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        F1_ATPASE_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    summary_path = declared.get("f1_observation_summary.csv")
    if summary_path is None:
        failures.append("F1 observation summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)

    root = _problem_root(F1_ATPASE_ID) / "curated"
    grouped: dict[str, list[tuple[float, float]]] = defaultdict(list)
    try:
        for row in _read_csv(root / "training_observations.csv"):
            dataset = {
                "turnover_rate": "turnover",
                "chemo_mechanical_coupling_efficiency": "coupling",
            }[row["measurement"]]
            grouped[dataset].append(
                (float(row["atp_concentration_molar"]), float(row["value"]))
            )
        for row in _read_csv(root / "nucleotide_binding_titrations.csv"):
            grouped[f"{row['condition'].casefold()}_binding"].append(
                (
                    10 ** float(row["log10_nucleotide_concentration"]),
                    float(row["bound_sites_per_enzyme"]),
                )
            )
        submitted_rows = _read_csv(summary_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        failures.append(f"Could not recompute F1 observations ({type(exc).__name__}).")
        return EvaluatorOutput(contract.summary, failures)

    expected: dict[str, tuple[int, float, float, float, float, float]] = {}
    for dataset, points in grouped.items():
        concentrations = [point[0] for point in points]
        values = [point[1] for point in points]
        expected[dataset] = (
            len(points),
            min(concentrations),
            max(concentrations),
            min(values),
            max(values),
            _spearman(concentrations, values),
        )
    submitted: dict[str, tuple[int, float, float, float, float, float]] = {}
    for row in submitted_rows:
        try:
            dataset = row["dataset"]
            value = (
                int(row["observation_count"]),
                float(row["min_concentration_molar"]),
                float(row["max_concentration_molar"]),
                float(row["min_observed_value"]),
                float(row["max_observed_value"]),
                float(row["spearman_concentration_value"]),
            )
        except (ValueError, KeyError):
            failures.append("F1 observation summary contains an invalid row.")
            continue
        if dataset in submitted:
            failures.append("F1 observation summary contains duplicate datasets.")
        submitted[dataset] = value
    if set(submitted) != set(expected):
        failures.append("F1 observation summary does not contain the exact dataset set.")
    mismatches = 0
    for dataset, target in expected.items():
        observed = submitted.get(dataset)
        if (
            observed is None
            or observed[0] != target[0]
            or any(
                not math.isclose(value, reference, rel_tol=1e-6, abs_tol=1e-9)
                for value, reference in zip(observed[1:], target[1:])
            )
        ):
            mismatches += 1
    if mismatches:
        failures.append(
            f"F1 observation summaries were not recomputed for {mismatches} datasets."
        )
    return EvaluatorOutput(
        f"{contract.summary}; recomputed_datasets={len(expected)}; "
        f"mismatches={mismatches}",
        list(dict.fromkeys(failures)),
    )


_PROTEIN_MUTATION_SUFFIX = re.compile(
    r"(?:_(?:del)?[A-Z*]\d+(?:[A-Z*]|del)?)+$",
    re.IGNORECASE,
)


def _protein_construct_group(name: str) -> str:
    value = _PROTEIN_MUTATION_SUFFIX.sub("", name.strip())
    value = re.sub(r"_(?:PG|hp)(?:_.*)?$", "", value, flags=re.IGNORECASE)
    return value.removesuffix(".pdb")


def _protein_resistance_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        PROTEIN_RESISTANCE_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    summary_path = declared.get("resistance_holdout_summary.csv")
    if summary_path is None:
        failures.append("Protein resistance holdout summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)

    root = _problem_root(PROTEIN_RESISTANCE_ID)
    try:
        fold_zero: set[str] = set()
        with (root / "curated" / "protein_group_folds.csv").open(
            newline="", encoding="utf-8"
        ) as handle:
            for row in csv.DictReader(handle):
                if row["fold"] == "0":
                    fold_zero.add(row["construct_group"])
        assay_rows = _read_csv(root / "curated" / "assay_conditions.csv")
        conditions: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
        for row in assay_rows:
            concentration = float(row["concentration_uM"])
            x_value = -12.0 if concentration == 0 else math.log10(concentration)
            conditions[(row["protease"], row["replicate"])].append(
                (row["column_suffix"], x_value)
            )
        for key in conditions:
            conditions[key].sort(
                key=lambda item: next(
                    int(row["dose_rank"])
                    for row in assay_rows
                    if row["column_suffix"] == item[0]
                )
            )

        accumulators: dict[
            tuple[str, str, str], tuple[float, int]
        ] = {}
        present_groups: set[str] = set()
        count_path = (
            root
            / "data"
            / "primary-observations"
            / "ngs-counts"
            / "NGS_count_lib1.csv"
        )
        with count_path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                group = _protein_construct_group(row["name"])
                if group not in fold_zero:
                    continue
                present_groups.add(group)
                for (protease, replicate), dose_conditions in conditions.items():
                    counts = [
                        float(row[f"v1_{suffix}"])
                        for suffix, _ in dose_conditions
                    ]
                    if counts[0] < 10 or sum(counts) < 20:
                        continue
                    x_values = [x_value for _, x_value in dose_conditions]
                    y_values = [
                        math.log2((count + 0.5) / (counts[0] + 0.5))
                        for count in counts
                    ]
                    area = sum(
                        (x_values[index] - x_values[index - 1])
                        * (y_values[index] + y_values[index - 1])
                        / 2
                        for index in range(1, len(x_values))
                    ) / (x_values[-1] - x_values[0])
                    key = (group, protease, replicate)
                    total, count = accumulators.get(key, (0.0, 0))
                    accumulators[key] = (total + area, count + 1)

        phenotypes: dict[str, dict[str, float]] = {
            "trypsin": {},
            "chymotrypsin": {},
        }
        replicate_mae: dict[str, list[float]] = {
            "trypsin": [],
            "chymotrypsin": [],
        }
        for group in present_groups:
            for protease in ("trypsin", "chymotrypsin"):
                first = accumulators.get((group, protease, "1"))
                second = accumulators.get((group, protease, "2"))
                if first is None or second is None:
                    continue
                first_value = first[0] / first[1]
                second_value = second[0] / second[1]
                phenotypes[protease][group] = (first_value + second_value) / 2
                replicate_mae[protease].append(
                    abs(first_value - second_value) / 2
                )
        common = sorted(
            set(phenotypes["trypsin"]) & set(phenotypes["chymotrypsin"])
        )
        cross_correlation = _spearman(
            [phenotypes["trypsin"][group] for group in common],
            [phenotypes["chymotrypsin"][group] for group in common],
        )
        expected: dict[
            tuple[str, str],
            tuple[int, int, float, float, float, float, float],
        ] = {}
        for protease in ("trypsin", "chymotrypsin"):
            values = list(phenotypes[protease].values())
            expected[("lib1", protease)] = (
                len(present_groups),
                len(values),
                _linear_quantile(values, 0.5),
                _linear_quantile(values, 0.1),
                _linear_quantile(values, 0.9),
                _linear_quantile(replicate_mae[protease], 0.5),
                0.0,
            )
        expected[("lib1", "cross")] = (
            len(present_groups),
            len(common),
            0.0,
            0.0,
            0.0,
            0.0,
            cross_correlation,
        )
        submitted_rows = _read_csv(summary_path)
    except (OSError, ValueError, KeyError, csv.Error, ZeroDivisionError) as exc:
        failures.append(
            f"Could not recompute protein resistance pilot ({type(exc).__name__})."
        )
        return EvaluatorOutput(contract.summary, failures)

    submitted: dict[
        tuple[str, str],
        tuple[int, int, float, float, float, float, float],
    ] = {}
    for row in submitted_rows:
        try:
            key = (row["library"], row["protease"])
            value = (
                int(row["fold0_group_count"]),
                int(row["qc_pass_groups"]),
                float(row["median_norm_log_survival_auc"]),
                float(row["q10_norm_log_survival_auc"]),
                float(row["q90_norm_log_survival_auc"]),
                float(row["replicate_mae_median"]),
                float(row["cross_protease_spearman"]),
            )
        except (ValueError, KeyError):
            failures.append("Protein resistance summary contains an invalid row.")
            continue
        if key in submitted:
            failures.append("Protein resistance summary contains duplicate keys.")
        submitted[key] = value
    if set(submitted) != set(expected):
        failures.append("Protein resistance summary does not contain the exact pilot rows.")
    mismatches = 0
    for key, target in expected.items():
        observed = submitted.get(key)
        if (
            observed is None
            or observed[:2] != target[:2]
            or any(
                not math.isclose(value, reference, rel_tol=1e-5, abs_tol=1e-7)
                for value, reference in zip(observed[2:], target[2:])
            )
        ):
            mismatches += 1
    if mismatches:
        failures.append(
            f"Protein resistance summaries were not recomputed for {mismatches} rows."
        )
    return EvaluatorOutput(
        f"{contract.summary}; fold0_groups={len(present_groups)}; "
        f"cross_groups={len(common)}; mismatches={mismatches}",
        list(dict.fromkeys(failures)),
    )


def _spontaneous_behavior_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        SPONTANEOUS_BEHAVIOR_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    submitted_path = declared.get("behavior_state_summary.csv")
    if submitted_path is None:
        failures.append("Behavior state summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)
    expected_sums: dict[tuple[str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0, 0.0]
    )
    try:
        source = (
            _problem_root(SPONTANEOUS_BEHAVIOR_ID)
            / "curated"
            / "behavior_events_pilot.csv.gz"
        )
        with gzip.open(source, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                key = (row["session_key"], row["stim_state"])
                expected_sums[key][0] += 1
                expected_sums[key][1] += float(row["velocity_2d_mm"])
                expected_sums[key][2] += float(row["photometry_z"])
        submitted_rows = _read_csv(submitted_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        failures.append(f"Could not recompute behavior pilot ({type(exc).__name__}).")
        return EvaluatorOutput(contract.summary, failures)
    expected = {
        key: (int(values[0]), values[1] / values[0], values[2] / values[0])
        for key, values in expected_sums.items()
    }
    submitted: dict[tuple[str, str], tuple[int, float, float]] = {}
    for row in submitted_rows:
        try:
            key = (row["session_key"], row["stim_state"])
            value = (
                int(row["frame_count"]),
                float(row["mean_velocity_2d_mm"]),
                float(row["mean_photometry_z"]),
            )
        except (ValueError, KeyError):
            failures.append("Behavior state summary contains an invalid row.")
            continue
        if key in submitted:
            failures.append("Behavior state summary contains duplicate keys.")
        submitted[key] = value
    if set(submitted) != set(expected):
        failures.append("Behavior state summary does not contain the exact group set.")
    mismatches = sum(
        submitted.get(key) is None
        or submitted[key][0] != target[0]
        or not math.isclose(submitted[key][1], target[1], rel_tol=1e-6, abs_tol=1e-8)
        or not math.isclose(submitted[key][2], target[2], rel_tol=1e-6, abs_tol=1e-8)
        for key, target in expected.items()
    )
    if mismatches:
        failures.append(
            f"Behavior summaries were not recomputed for {mismatches} groups."
        )
    return EvaluatorOutput(
        f"{contract.summary}; recomputed_groups={len(expected)}; mismatches={mismatches}",
        list(dict.fromkeys(failures)),
    )


def _tracebind_fragment_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(TRACEBIND_ID, manifest_path, artifact_root, manifest_verified)
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    submitted_path = declared.get("peak_fragment_summary.csv")
    if submitted_path is None:
        failures.append("Peak fragment summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)
    root = _problem_root(TRACEBIND_ID) / "curated"
    try:
        peaks = _read_csv(root / "pilot_peaks.csv")
        fragments: list[tuple[str, int, int, int]] = []
        with gzip.open(
            root / "pilot_fragments.csv.gz", "rt", newline="", encoding="utf-8"
        ) as handle:
            for row in csv.DictReader(handle):
                fragments.append(
                    (
                        row["chromosome"],
                        int(row["start"]),
                        int(row["end"]),
                        int(row["count"]),
                    )
                )
        submitted_rows = _read_csv(submitted_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        failures.append(f"Could not recompute TraceBIND pilot ({type(exc).__name__}).")
        return EvaluatorOutput(contract.summary, failures)
    expected: dict[str, tuple[int, int, int]] = {}
    for peak in peaks:
        chromosome = peak["chromosome"]
        start, end = int(peak["start"]), int(peak["end"])
        overlapping = 0
        weighted = 0
        endpoints = 0
        for fragment_chromosome, fragment_start, fragment_end, count in fragments:
            if fragment_chromosome != chromosome or fragment_end <= start or fragment_start >= end:
                continue
            overlapping += 1
            weighted += count
            endpoints += count * (
                int(start <= fragment_start < end) + int(start <= fragment_end < end)
            )
        expected[peak["peak_id"]] = (overlapping, weighted, endpoints)
    submitted: dict[str, tuple[int, int, int]] = {}
    for row in submitted_rows:
        try:
            key = row["peak_id"]
            value = (
                int(row["overlapping_fragment_rows"]),
                int(row["weighted_fragment_count"]),
                int(row["insertion_endpoint_count"]),
            )
        except (ValueError, KeyError):
            failures.append("Peak fragment summary contains an invalid row.")
            continue
        if key in submitted:
            failures.append("Peak fragment summary contains duplicate peak IDs.")
        submitted[key] = value
    if set(submitted) != set(expected):
        failures.append("Peak fragment summary does not contain the exact peak set.")
    mismatches = sum(submitted.get(key) != target for key, target in expected.items())
    if mismatches:
        failures.append(f"Peak fragment summaries mismatch for {mismatches} peaks.")
    return EvaluatorOutput(
        f"{contract.summary}; recomputed_peaks={len(expected)}; mismatches={mismatches}",
        list(dict.fromkeys(failures)),
    )


def _mitochondria_rna_evaluator(
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput:
    contract = _combine_contract(
        MITO_NUCLEAR_PORE_ID, manifest_path, artifact_root, manifest_verified
    )
    _, declared, declaration_failures = _declared_artifacts(
        manifest_path, artifact_root, manifest_verified
    )
    failures = [*contract.failures, *declaration_failures]
    submitted_path = declared.get("rna_library_summary.csv")
    if submitted_path is None:
        failures.append("RNA library summary was not declared.")
        return EvaluatorOutput(contract.summary, failures)
    source = (
        _problem_root(MITO_NUCLEAR_PORE_ID)
        / "data"
        / "acquired"
        / "geo"
        / "GSE325290_ALL.GRCm38_99.rsem.genes.results.txt.gz"
    )
    samples = ("RKO1", "RKO2", "RKO3", "WT1", "WT2", "WT3")
    totals = {sample: 0.0 for sample in samples}
    detected = {sample: 0 for sample in samples}
    gene_count = 0
    try:
        with gzip.open(source, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                gene_count += 1
                for sample in samples:
                    value = float(row[sample])
                    totals[sample] += value
                    detected[sample] += int(value > 0)
        submitted_rows = _read_csv(submitted_path)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        failures.append(f"Could not recompute RNA library audit ({type(exc).__name__}).")
        return EvaluatorOutput(contract.summary, failures)
    expected = {
        sample: (gene_count, detected[sample], totals[sample]) for sample in samples
    }
    submitted: dict[str, tuple[int, int, float]] = {}
    for row in submitted_rows:
        try:
            key = row["sample"]
            value = (
                int(row["gene_rows"]),
                int(row["detected_genes"]),
                float(row["total_expected_count"]),
            )
        except (ValueError, KeyError):
            failures.append("RNA library summary contains an invalid row.")
            continue
        if key in submitted:
            failures.append("RNA library summary contains duplicate samples.")
        submitted[key] = value
    if set(submitted) != set(expected):
        failures.append("RNA library summary does not contain the exact sample set.")
    mismatches = sum(
        submitted.get(sample) is None
        or submitted[sample][:2] != target[:2]
        or not math.isclose(submitted[sample][2], target[2], rel_tol=1e-9, abs_tol=1e-6)
        for sample, target in expected.items()
    )
    if mismatches:
        failures.append(f"RNA library summaries mismatch for {mismatches} samples.")
    return EvaluatorOutput(
        f"{contract.summary}; recomputed_samples={len(expected)}; mismatches={mismatches}",
        list(dict.fromkeys(failures)),
    )


register_evaluator(GASTRULATION_ID, _gastrulation_evaluator)
register_evaluator(RNA_HYDRATION_ID, _rna_hydration_evaluator)
register_evaluator(RIVER_METHANE_ID, _river_methane_evaluator)
register_evaluator(HUMAN_MASS_ID, _human_mass_evaluator)
register_evaluator(CHROMATIN_ID, _chromatin_pilot_evaluator)
register_evaluator(F1_ATPASE_ID, _f1_observation_evaluator)
register_evaluator(PROTEIN_RESISTANCE_ID, _protein_resistance_evaluator)
register_evaluator(SPONTANEOUS_BEHAVIOR_ID, _spontaneous_behavior_evaluator)
register_evaluator(TRACEBIND_ID, _tracebind_fragment_evaluator)
register_evaluator(MITO_NUCLEAR_PORE_ID, _mitochondria_rna_evaluator)
