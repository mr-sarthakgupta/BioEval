from __future__ import annotations

import array
import csv
import gzip
import hashlib
import json
import math
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


register_evaluator(GASTRULATION_ID, _gastrulation_evaluator)
register_evaluator(RNA_HYDRATION_ID, _rna_hydration_evaluator)
register_evaluator(RIVER_METHANE_ID, _river_methane_evaluator)
