from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from bioeval.problems import load_problem_spec, resolve_problem_root
from bioeval.schemas import JudgeResult


@dataclass
class EvaluatorOutput:
    summary: str
    failures: list[str] = field(default_factory=list)


Evaluator = Callable[[Path | None, Path | None, bool], EvaluatorOutput]
_REGISTRY: dict[str, Evaluator] = {}


def register_evaluator(problem_id: str, evaluator: Evaluator) -> None:
    if problem_id in _REGISTRY:
        raise ValueError(f"Evaluator already registered: {problem_id}")
    _REGISTRY[problem_id] = evaluator


def _safe_artifact(root: Path, relative: str) -> Path | None:
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _problem_root(problem_id: str) -> Path | None:
    return resolve_problem_root(problem_id)


def _load_rules(problem_id: str) -> dict:
    root = _problem_root(problem_id)
    path = root / "evaluator" / "artifact_rules.json" if root else None
    if path is None or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"_load_error": f"{type(exc).__name__}: {exc}"}
    if not isinstance(value, dict):
        return {"_load_error": "artifact rules root is not an object"}
    if set(value) != {"artifacts"} or not isinstance(value.get("artifacts"), dict):
        return {"_load_error": "artifact rules must contain exactly one artifacts object"}
    allowed_rule_keys = {
        "numeric_bounds",
        "minimum_unique",
        "allowed_values",
        "required_values",
        "ordered_columns",
    }
    for artifact, rules in value["artifacts"].items():
        if not isinstance(artifact, str) or not isinstance(rules, dict):
            return {"_load_error": "artifact rule entries must be named objects"}
        unknown = set(rules) - allowed_rule_keys
        if unknown:
            return {
                "_load_error": (
                    f"unsupported rules for {artifact}: {', '.join(sorted(unknown))}"
                )
            }
    return value


def _contract_evaluator(problem_id: str) -> Evaluator:
    def evaluate(
        manifest_path: Path | None,
        artifact_root: Path | None,
        manifest_verified: bool,
    ) -> EvaluatorOutput:
        prefix = f"Evaluator-verified {problem_id}:"
        spec = load_problem_spec(problem_id)
        if not spec.required_artifacts:
            return EvaluatorOutput(f"{prefix} no artifact contract declared.")
        if not manifest_verified or manifest_path is None:
            return EvaluatorOutput(
                f"{prefix} unavailable because the analysis manifest was not verified.",
                ["Required analysis manifest was missing or invalid."],
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return EvaluatorOutput(
                f"{prefix} analysis manifest could not be read.",
                ["Required analysis manifest could not be read."],
            )
        root = (artifact_root or manifest_path.parent).resolve()
        declared = {
            item.get("path"): _safe_artifact(root, item.get("path", ""))
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        }
        rule_document = _load_rules(problem_id)
        failures: list[str] = []
        if rule_document.get("_load_error"):
            failures.append(
                f"Could not load evaluator artifact rules: "
                f"{rule_document['_load_error']}."
            )
        rules = rule_document.get("artifacts", {})
        summaries: list[str] = []
        for contract in spec.required_artifacts:
            path = declared.get(contract.path)
            if path is None:
                failures.append(f"Missing required artifact: {contract.path}.")
                continue
            try:
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    fieldnames = reader.fieldnames or []
                    fields = set(fieldnames)
                    rows = list(reader)
            except (OSError, csv.Error, UnicodeError):
                failures.append(f"Could not parse required CSV artifact: {contract.path}.")
                continue
            missing = set(contract.columns) - fields
            extra = fields - set(contract.columns)
            forbidden = set(contract.forbidden_columns) & fields
            if missing:
                failures.append(
                    f"{contract.path} missing columns: {', '.join(sorted(missing))}."
                )
            if forbidden:
                failures.append(
                    f"{contract.path} contains forbidden columns: {', '.join(sorted(forbidden))}."
                )
            if extra:
                failures.append(
                    f"{contract.path} contains undeclared columns: "
                    f"{', '.join(sorted(extra))}."
                )
            if len(fieldnames) != len(fields):
                failures.append(f"{contract.path} contains duplicate column names.")
            overflow = sum(None in row for row in rows)
            if overflow:
                failures.append(
                    f"{contract.path} has {overflow} row(s) with extra CSV fields."
                )
            serialized_rows = [
                json.dumps(
                    {str(key): value for key, value in row.items()},
                    sort_keys=True,
                    separators=(",", ":"),
                )
                for row in rows
            ]
            duplicate_rows = len(serialized_rows) - len(set(serialized_rows))
            if duplicate_rows:
                failures.append(
                    f"{contract.path} has {duplicate_rows} duplicate row(s)."
                )
            if len(rows) < contract.min_rows:
                failures.append(
                    f"{contract.path} has {len(rows)} rows; requires {contract.min_rows}."
                )
            artifact_rules = rules.get(contract.path, {})
            for column, bounds in artifact_rules.get("numeric_bounds", {}).items():
                values: list[float] = []
                invalid_values = 0
                for row in rows:
                    try:
                        value = float(row[column])
                    except (KeyError, TypeError, ValueError):
                        invalid_values += 1
                        continue
                    if math.isfinite(value):
                        values.append(value)
                    else:
                        invalid_values += 1
                if invalid_values:
                    failures.append(
                        f"{contract.path}:{column} has {invalid_values} "
                        f"non-numeric or non-finite values."
                    )
                if not values:
                    failures.append(f"{contract.path}:{column} has no finite values.")
                    continue
                if "min" in bounds and min(values) < float(bounds["min"]):
                    failures.append(f"{contract.path}:{column} falls below its allowed bound.")
                if "max" in bounds and max(values) > float(bounds["max"]):
                    failures.append(f"{contract.path}:{column} exceeds its allowed bound.")
            for column, minimum in artifact_rules.get("minimum_unique", {}).items():
                unique = {row.get(column, "") for row in rows if row.get(column, "") != ""}
                if len(unique) < int(minimum):
                    failures.append(
                        f"{contract.path}:{column} has {len(unique)} unique values; "
                        f"requires {minimum}."
                    )
            for column, allowed in artifact_rules.get("allowed_values", {}).items():
                unexpected = {
                    row.get(column, "")
                    for row in rows
                    if row.get(column, "") not in set(map(str, allowed))
                }
                if unexpected:
                    failures.append(
                        f"{contract.path}:{column} contains disallowed values: "
                        f"{', '.join(sorted(unexpected))}."
                    )
            for column, required in artifact_rules.get("required_values", {}).items():
                observed = {row.get(column, "") for row in rows}
                missing_values = set(map(str, required)) - observed
                if missing_values:
                    failures.append(
                        f"{contract.path}:{column} is missing required values: "
                        f"{', '.join(sorted(missing_values))}."
                    )
            for ordered in artifact_rules.get("ordered_columns", []):
                if not isinstance(ordered, list) or len(ordered) < 2:
                    continue
                for row_number, row in enumerate(rows, start=2):
                    try:
                        values = [float(row[column]) for column in ordered]
                    except (KeyError, TypeError, ValueError):
                        failures.append(
                            f"{contract.path}:row {row_number} has non-numeric "
                            f"ordered columns."
                        )
                        continue
                    if any(not math.isfinite(value) for value in values) or values != sorted(values):
                        failures.append(
                            f"{contract.path}:row {row_number} violates ordering "
                            f"{' <= '.join(ordered)}."
                        )
            summaries.append(f"{contract.path}={len(rows)} rows")
        return EvaluatorOutput(
            f"{prefix} " + "; ".join(summaries or ["no valid artifacts"]),
            failures,
        )

    return evaluate


def evaluate_problem_artifacts(
    problem_id: str,
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> EvaluatorOutput | None:
    evaluator = _REGISTRY.get(problem_id)
    if evaluator is None:
        spec = load_problem_spec(problem_id)
        if not spec.required_artifacts:
            return None
        evaluator = _contract_evaluator(problem_id)
    return evaluator(manifest_path, artifact_root, manifest_verified)


def apply_evaluator_gate(
    result: JudgeResult,
    output: EvaluatorOutput | None,
) -> JudgeResult:
    if output is None or not output.failures:
        return result
    result.execution_score = 0.0
    result.score = min(result.score, 0.49)
    result.verdict = "fail"
    result.evidence_validation.extend(output.failures)
    return result
