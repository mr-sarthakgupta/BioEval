from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
import statistics
import sys
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

from bioeval.bedrock_client import (
    DEFAULT_BEDROCK_API_BASE,
    create_bedrock_client,
    ensure_bedrock_bearer_token,
    messages_with_cache_point,
    prompt_cache_point,
    extract_text_from_response,
)
from bioeval.bedrock_cost import BedrockCostTracker
from bioeval.evaluators import apply_evaluator_gate, evaluate_problem_artifacts
from bioeval.problems import load_problem_spec, resolve_problem_root
from bioeval.search_proxy import contains_hidden_identifier
from bioeval.run_record import append_jsonl, utc_now, write_json
from bioeval.schemas import CaveatScore, ConclusionScore, EvidenceCitation, JudgeResult


DEFAULT_JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"
FORGE_PROBLEM_ID = "s41467-026-73977-2_forge-cancer-drug-response"
IDR_PROBLEM_ID = "s41589-026-02251-9_idr-condensate-serine-charge"
F1_PROBLEM_ID = "s41467-026-73844-0_f1-atpase-markov-model"
BUTTERFLY_PROBLEM_ID = "s41467-026-73635-7_butterfly-longevity-pollen-feeding"

JUDGE_SYSTEM_PROMPT = """You are a strict scientific-discovery benchmark judge.

You compare an under-eval-agent's (UEA) final answer against hidden expected
conclusions from the original research paper. The UEA never saw the paper; it had a
general problem statement, internet access, and a guarded experiment-agent.

Classify each expected conclusion independently:
- "matched": correct directionality and directly supported by submitted analysis evidence.
- "partial": the right idea is present but incomplete or only partly supported.
- "missing": not addressed or unsupported by analysis evidence.
- "wrong": addressed with the opposite or contradicted claim.

Evidence rules:
- Copy every expected conclusion and caveat EXACTLY into its output row.
- Every matched/partial conclusion must include short VERBATIM citations from transcript
  command output, a data excerpt, an analysis result, or a submitted artifact.
- Final-answer prose alone is not evidence for a scientific conclusion.
- Caveats may cite the final answer because caveat handling is itself a prose property.
- Keep quotes short and exact. Artifact citations require a relative artifact_path.
- Python verifies all quotes and deterministically downgrades unsupported rows.
- Do not reward name-dropping, generic domain knowledge, or unsupported numeric claims.
- Do not compute score, verdict, or summary lists; Python derives them.

Leakage check:
- Set leakage_suspected when the answer reproduces an exact hidden title, DOI, author,
  repository, or a paper-specific value unsupported by granted data or analysis.
- Explain the concrete evidence in leakage_rationale. Python applies disqualification.

Return ONLY JSON matching the provided output_schema.
"""


JUDGE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "per_conclusion": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "conclusion": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["matched", "partial", "missing", "wrong"],
                    },
                    "evidence": {"type": "string"},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "source": {
                                    "type": "string",
                                    "enum": ["transcript", "final_answer", "artifact"],
                                },
                                "evidence_kind": {
                                    "type": "string",
                                    "enum": [
                                        "command_output",
                                        "data_excerpt",
                                        "analysis_result",
                                        "final_claim",
                                        "artifact",
                                    ],
                                },
                                "quote": {"type": "string"},
                                "artifact_path": {"type": ["string", "null"]},
                            },
                            "required": ["source", "evidence_kind", "quote", "artifact_path"],
                        },
                    },
                },
                "required": ["conclusion", "status", "evidence", "citations"],
            },
        },
        "per_caveat": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "caveat": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["addressed", "partial", "missing"],
                    },
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "source": {
                                    "type": "string",
                                    "enum": ["transcript", "final_answer", "artifact"],
                                },
                                "evidence_kind": {
                                    "type": "string",
                                    "enum": [
                                        "command_output",
                                        "data_excerpt",
                                        "analysis_result",
                                        "final_claim",
                                        "artifact",
                                    ],
                                },
                                "quote": {"type": "string"},
                                "artifact_path": {"type": ["string", "null"]},
                            },
                            "required": ["source", "evidence_kind", "quote", "artifact_path"],
                        },
                    },
                },
                "required": ["caveat", "status", "citations"],
            },
        },
        "leakage_suspected": {"type": "boolean"},
        "leakage_rationale": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": [
        "per_conclusion",
        "per_caveat",
        "leakage_suspected",
        "leakage_rationale",
        "rationale",
    ],
}


def read_optional(path: Path | None) -> str | None:
    if not path:
        return None
    return path.read_text(errors="replace")


def _forge_hidden_holdout_summary(
    *,
    problem_id: str,
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> str | None:
    if problem_id != FORGE_PROBLEM_ID:
        return None
    prefix = "Evaluator-verified FORGE hidden holdout:"
    if not manifest_verified or manifest_path is None:
        return f"{prefix} unavailable because the analysis manifest was not verified."
    try:
        manifest = json.loads(manifest_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return f"{prefix} unavailable because the analysis manifest could not be read."

    root = artifact_root or manifest_path.parent
    prediction_path: Path | None = None
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        candidate = _safe_artifact_path(root, item.get("path"))
        if candidate is not None and candidate.name == "forge_predictions.csv":
            prediction_path = candidate
            break
    if prediction_path is None:
        return f"{prefix} missing declared forge_predictions.csv."

    labels_path = (
        Path(__file__).resolve().parents[2]
        / "problems_complete"
        / FORGE_PROBLEM_ID
        / "evaluator"
        / "drug_response_test_labels.csv"
    )
    training_path = labels_path.parents[1] / "curated" / "drug_response_train.csv"
    required = {
        "drug",
        "cell_line_id",
        "baseline_prediction",
        "dependency_informed_prediction",
        "therapeutic_benefit_score",
    }
    forbidden = {"observed_ic50", "ic50", "label", "outcome"}
    try:
        with labels_path.open(newline="") as handle:
            labels = {
                (row["drug"], row["cell_line_id"]): float(row["observed_ic50"])
                for row in csv.DictReader(handle)
            }
        training_by_drug: dict[str, list[float]] = {}
        with training_path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                training_by_drug.setdefault(row["drug"], []).append(
                    float(row["observed_ic50"])
                )
        frozen_baseline = {
            drug: sum(values) / len(values)
            for drug, values in training_by_drug.items()
            if values
        }
        with prediction_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or [])
            if not required.issubset(fields) or forbidden & fields:
                return (
                    f"{prefix} invalid prediction schema; required columns were missing "
                    "or a held-out outcome column was included."
                )
            predictions: dict[tuple[str, str], tuple[float, float, float]] = {}
            duplicates = 0
            unknown = 0
            for row in reader:
                key = (row["drug"], row["cell_line_id"])
                if key in predictions:
                    duplicates += 1
                    continue
                if key not in labels:
                    unknown += 1
                    continue
                baseline = float(row["baseline_prediction"])
                informed = float(row["dependency_informed_prediction"])
                benefit = float(row["therapeutic_benefit_score"])
                if not all(math.isfinite(value) for value in (baseline, informed, benefit)):
                    continue
                predictions[key] = (baseline, informed, benefit)
    except (OSError, ValueError, KeyError, csv.Error) as exc:
        return f"{prefix} could not score predictions ({type(exc).__name__})."

    if not predictions:
        return f"{prefix} no valid held-out predictions."
    baseline_sq = []
    informed_sq = []
    baseline_abs = []
    informed_abs = []
    reference_sq = []
    reference_abs = []
    for key, (baseline, informed, _benefit) in predictions.items():
        observed = labels[key]
        baseline_sq.append((baseline - observed) ** 2)
        informed_sq.append((informed - observed) ** 2)
        baseline_abs.append(abs(baseline - observed))
        informed_abs.append(abs(informed - observed))
        reference = frozen_baseline.get(key[0])
        if reference is None:
            return f"{prefix} frozen baseline is unavailable for {key[0]}."
        reference_sq.append((reference - observed) ** 2)
        reference_abs.append(abs(reference - observed))
    baseline_rmse = math.sqrt(sum(baseline_sq) / len(baseline_sq))
    informed_rmse = math.sqrt(sum(informed_sq) / len(informed_sq))
    baseline_mae = sum(baseline_abs) / len(baseline_abs)
    informed_mae = sum(informed_abs) / len(informed_abs)
    reference_rmse = math.sqrt(sum(reference_sq) / len(reference_sq))
    reference_mae = sum(reference_abs) / len(reference_abs)
    egfr_rows = [
        (cell, informed, benefit)
        for (drug, cell), (_baseline, informed, benefit) in predictions.items()
        if re.sub(r"[^a-z0-9]", "", drug.casefold()) == "erlotinib"
    ]
    dependency_by_cell: dict[str, float] = {}
    dependency_path = labels_path.parents[1] / "data" / "figshare" / "31268542" / "Dep.csv"
    if egfr_rows:
        wanted = {cell for cell, _informed, _benefit in egfr_rows}
        try:
            with dependency_path.open(newline="") as handle:
                reader = csv.reader(handle)
                header = next(reader)
                egfr_index = header.index("EGFR")
                for row in reader:
                    if row and row[0] in wanted and row[egfr_index]:
                        dependency_by_cell[row[0]] = float(row[egfr_index])
        except (OSError, ValueError, csv.Error):
            dependency_by_cell = {}

    def correlation(left: list[float], right: list[float]) -> float:
        if len(left) < 3 or len(left) != len(right):
            return math.nan
        left_mean = sum(left) / len(left)
        right_mean = sum(right) / len(right)
        numerator = sum(
            (x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True)
        )
        denominator = math.sqrt(
            sum((x - left_mean) ** 2 for x in left)
            * sum((y - right_mean) ** 2 for y in right)
        )
        return numerator / denominator if denominator else math.nan

    aligned = [
        (dependency_by_cell[cell], informed, benefit)
        for cell, informed, benefit in egfr_rows
        if cell in dependency_by_cell
    ]
    benefit_dependency_r = correlation(
        [row[2] for row in aligned],
        [row[0] for row in aligned],
    )
    benefit_ic50_r = correlation(
        [row[2] for row in aligned],
        [row[1] for row in aligned],
    )
    return (
        f"{prefix} coverage={len(predictions)}/{len(labels)}; duplicates={duplicates}; "
        f"unknown_rows={unknown}; baseline_RMSE={baseline_rmse:.6g}; "
        f"dependency_RMSE={informed_rmse:.6g}; baseline_MAE={baseline_mae:.6g}; "
        f"dependency_MAE={informed_mae:.6g}; frozen_RMSE={reference_rmse:.6g}; "
        f"frozen_MAE={reference_mae:.6g}; EGFR_erlotinib_n={len(aligned)}; "
        f"benefit_dependency_r={benefit_dependency_r:.6g}; "
        f"benefit_IC50_r={benefit_ic50_r:.6g}."
    )


def _idr_hidden_holdout_summary(
    *,
    problem_id: str,
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> str | None:
    if problem_id != IDR_PROBLEM_ID:
        return None
    prefix = "Evaluator-verified IDR hidden holdout:"
    if not manifest_verified or manifest_path is None:
        return f"{prefix} unavailable because the analysis manifest was not verified."
    try:
        manifest = json.loads(manifest_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return f"{prefix} unavailable because the analysis manifest could not be read."
    root = artifact_root or manifest_path.parent
    prediction_path = next(
        (
            candidate
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict)
            and (candidate := _safe_artifact_path(root, item.get("path"))) is not None
            and candidate.name == "idr_predictions.csv"
        ),
        None,
    )
    if prediction_path is None:
        return f"{prefix} missing declared idr_predictions.csv."

    problem_root = resolve_problem_root(IDR_PROBLEM_ID)
    if problem_root is None:
        return f"{prefix} unavailable because the problem root is missing."
    labels_path = problem_root / "evaluator" / "perturbation_test_labels.csv"
    training_path = problem_root / "curated" / "perturbation_training.csv"
    key_columns = ("assay", "pair", "group", "replicate")
    try:
        with labels_path.open(newline="") as handle:
            labels = {
                tuple(row[column] for column in key_columns): float(row["observed_pearson_r"])
                for row in csv.DictReader(handle)
            }
        with training_path.open(newline="") as handle:
            training = [
                float(row["observed_pearson_r"])
                for row in csv.DictReader(handle)
            ]
        training_mean = sum(training) / len(training)
        predictions: dict[tuple[str, ...], float] = {}
        duplicates = 0
        unknown = 0
        with prediction_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            required = {*key_columns, "predicted_pearson_r"}
            if not required.issubset(set(reader.fieldnames or [])):
                return f"{prefix} invalid prediction schema."
            for row in reader:
                key = tuple(row[column] for column in key_columns)
                if key in predictions:
                    duplicates += 1
                    continue
                if key not in labels:
                    unknown += 1
                    continue
                value = float(row["predicted_pearson_r"])
                if math.isfinite(value):
                    predictions[key] = value
    except (OSError, ValueError, KeyError, csv.Error, ZeroDivisionError) as exc:
        return f"{prefix} could not score predictions ({type(exc).__name__})."
    if not predictions:
        return f"{prefix} no valid held-out predictions."
    model_rmse = math.sqrt(
        sum((predictions[key] - labels[key]) ** 2 for key in predictions) / len(predictions)
    )
    baseline_rmse = math.sqrt(
        sum((training_mean - labels[key]) ** 2 for key in predictions) / len(predictions)
    )
    return (
        f"{prefix} coverage={len(predictions)}/{len(labels)}; duplicates={duplicates}; "
        f"unknown_rows={unknown}; baseline_RMSE={baseline_rmse:.6g}; "
        f"model_RMSE={model_rmse:.6g}."
    )


def _f1_model_selection_summary(
    *,
    problem_id: str,
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> str | None:
    if problem_id != F1_PROBLEM_ID:
        return None
    prefix = "Evaluator-verified F1 model selection:"
    if not manifest_verified or manifest_path is None:
        return f"{prefix} unavailable because the analysis manifest was not verified."
    try:
        manifest = json.loads(manifest_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return f"{prefix} unavailable because the analysis manifest could not be read."
    root = artifact_root or manifest_path.parent
    summary_path = next(
        (
            candidate
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict)
            and (candidate := _safe_artifact_path(root, item.get("path"))) is not None
            and candidate.name == "f1_model_summary.csv"
        ),
        None,
    )
    if summary_path is None:
        return f"{prefix} missing declared f1_model_summary.csv."
    required = {
        "model_id",
        "conformation_count",
        "training_standardized_rmse",
        "maximum_standardized_residual",
        "parameter_count",
        "n_training_observations",
        "bic",
        "validation_constraints_passed",
        "validation_constraints_total",
    }
    rows: list[dict] = []
    invalid = 0
    try:
        with summary_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if not required.issubset(set(reader.fieldnames or [])):
                return f"{prefix} invalid model-summary schema."
            for row in reader:
                parsed = {
                    "conformations": int(row["conformation_count"]),
                    "rmse": float(row["training_standardized_rmse"]),
                    "maximum": float(row["maximum_standardized_residual"]),
                    "parameters": int(row["parameter_count"]),
                    "n": int(row["n_training_observations"]),
                    "bic": float(row["bic"]),
                    "passed": int(row["validation_constraints_passed"]),
                    "total": int(row["validation_constraints_total"]),
                }
                if parsed["n"] <= 0 or parsed["parameters"] < 0 or parsed["rmse"] <= 0:
                    invalid += 1
                    continue
                expected_bic = (
                    parsed["n"] * math.log(parsed["rmse"] ** 2)
                    + parsed["parameters"] * math.log(parsed["n"])
                )
                if abs(parsed["bic"] - expected_bic) > max(0.1, abs(expected_bic) * 1e-3):
                    invalid += 1
                    continue
                rows.append(parsed)
    except (OSError, ValueError, KeyError, csv.Error):
        return f"{prefix} could not validate the model summary."
    fitted = [
        row for row in rows
        if row["rmse"] <= 1.5 and row["maximum"] <= 3.0 and row["total"] == 9
    ]
    three = [row for row in fitted if row["conformations"] == 3]
    four = [
        row for row in fitted
        if row["conformations"] == 4 and row["passed"] == row["total"]
    ]
    three_all_fail = bool(three) and all(row["passed"] < row["total"] for row in three)
    bic_delta = (
        min(row["bic"] for row in four) - min(row["bic"] for row in three)
        if three and four
        else math.inf
    )
    return (
        f"{prefix} three_fitted={len(three)}; three_all_fail={int(three_all_fail)}; "
        f"four_passing={len(four)}; four_minus_three_BIC={bic_delta:.6g}; "
        f"invalid_rows={invalid}."
    )


def _butterfly_survival_summary(
    *,
    problem_id: str,
    manifest_path: Path | None,
    artifact_root: Path | None,
    manifest_verified: bool,
) -> str | None:
    if problem_id != BUTTERFLY_PROBLEM_ID:
        return None
    prefix = "Evaluator-verified butterfly survival metrics:"
    if not manifest_verified or manifest_path is None:
        return f"{prefix} unavailable because the analysis manifest was not verified."
    try:
        manifest = json.loads(manifest_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return f"{prefix} unavailable because the analysis manifest could not be read."
    root = artifact_root or manifest_path.parent
    metrics_path = next(
        (
            candidate
            for item in manifest.get("artifacts", [])
            if isinstance(item, dict)
            and (candidate := _safe_artifact_path(root, item.get("path"))) is not None
            and candidate.name == "butterfly_metrics.csv"
        ),
        None,
    )
    if metrics_path is None:
        return f"{prefix} missing declared butterfly_metrics.csv."
    resolved_root = resolve_problem_root(BUTTERFLY_PROBLEM_ID)
    if resolved_root is None:
        return f"{prefix} unavailable because the problem root is missing."
    problem_root = resolved_root / "curated" / "observations"

    def km_median(rows: list[dict[str, str]]) -> float:
        times = sorted({float(row["Age"]) for row in rows if row["Age"]})
        survival = 1.0
        for time_value in times:
            at_risk = sum(float(row["Age"]) >= time_value for row in rows)
            events = sum(
                float(row["Age"]) == time_value and row["Status"] == "1"
                for row in rows
            )
            if at_risk:
                survival *= 1 - events / at_risk
            if survival <= 0.5:
                return time_value
        return math.inf

    def percentile(values: list[float], fraction: float) -> float:
        ordered = sorted(values)
        index = min(len(ordered) - 1, max(0, int(fraction * len(ordered))))
        return ordered[index]

    def bootstrap_interval(
        values: list[object],
        statistic: Callable[[list[object]], float],
        rng: random.Random,
        replicates: int = 1000,
    ) -> tuple[float, float]:
        sampled = [
            statistic([values[rng.randrange(len(values))] for _ in values])
            for _ in range(replicates)
        ]
        return percentile(sampled, 0.025), percentile(sampled, 0.975)

    def ols_slope(points: list[tuple[float, float]]) -> float:
        x_mean = sum(point[0] for point in points) / len(points)
        y_mean = sum(point[1] for point in points) / len(points)
        denominator = sum((point[0] - x_mean) ** 2 for point in points)
        if denominator == 0:
            raise ZeroDivisionError
        return (
            sum(
                (point[0] - x_mean) * (point[1] - y_mean)
                for point in points
            )
            / denominator
        )

    def log_hazard_slope(rows: list[dict[str, str]]) -> float:
        times = sorted(
            {
                float(row["Age"])
                for row in rows
                if row["Age"] and 7 <= float(row["Age"]) <= 90
            }
        )
        cumulative = 0.0
        points: list[tuple[float, float]] = []
        for time_value in times:
            at_risk = sum(float(row["Age"]) >= time_value for row in rows)
            events = sum(
                float(row["Age"]) == time_value and row["Status"] == "1"
                for row in rows
            )
            if at_risk and events:
                cumulative += events / at_risk
                if cumulative > 0:
                    points.append((time_value, math.log(cumulative)))
        if len(points) < 3:
            raise ValueError("insufficient hazard points")
        return ols_slope(points)

    def individual_grip_slopes(
        rows: list[dict[str, str]],
        species: str,
    ) -> list[float]:
        grouped: dict[str, list[tuple[float, float]]] = {}
        for row in rows:
            if (
                row["Species"] != species
                or not row["Max_GS"]
                or row["Age_weeks"] not in {"1", "3", "5"}
            ):
                continue
            grouped.setdefault(row["ID"], []).append(
                (float(row["Age_weeks"]), float(row["Max_GS"]))
            )
        return [
            ols_slope(points)
            for points in grouped.values()
            if len({point[0] for point in points}) >= 2
        ]

    try:
        with (problem_root / "species_max_lifespan.csv").open(newline="") as handle:
            lifespan = list(csv.DictReader(handle))
        pollen = sorted(
            float(row["Max_lifespan"])
            for row in lifespan
            if row["Feeding_habit"] == "PF"
        )
        non_pollen = sorted(
            float(row["Max_lifespan"])
            for row in lifespan
            if row["Feeding_habit"] == "NPF"
        )
        rng = random.Random(73635)
        ratio = statistics.median(pollen) / statistics.median(non_pollen)
        ratio_samples: list[float] = []
        for _ in range(1000):
            sampled_pollen = [pollen[rng.randrange(len(pollen))] for _ in pollen]
            sampled_non_pollen = [
                non_pollen[rng.randrange(len(non_pollen))] for _ in non_pollen
            ]
            ratio_samples.append(
                statistics.median(sampled_pollen)
                / statistics.median(sampled_non_pollen)
            )
        expected: dict[str, tuple[float, float, float]] = {
            "median_species_max_ratio": (
                ratio,
                percentile(ratio_samples, 0.025),
                percentile(ratio_samples, 0.975),
            ),
            "maximum_verified_lifespan_days": (
                max(pollen + non_pollen),
                max(pollen + non_pollen),
                max(pollen + non_pollen),
            ),
        }
        with (problem_root / "diet_survival.csv").open(newline="") as handle:
            diet_rows = [
                row
                for row in csv.DictReader(handle)
                if row["Age"] and float(row["Age"]) != 0
            ]
        for species in ("Hecale", "Dryas"):
            for diet in ("PF", "PD"):
                subset = [
                    row
                    for row in diet_rows
                    if row["Species"] == species and row["Diet"] == diet
                ]
                value = km_median(subset)
                lower, upper = bootstrap_interval(
                    list(subset),
                    lambda sample: km_median(sample),  # type: ignore[arg-type]
                    rng,
                )
                expected[f"{species.casefold()}_{diet.casefold()}_km_median_days"] = (
                    value,
                    lower,
                    upper,
                )
        hazard_values: dict[str, float] = {}
        for species in ("Hecale", "Dryas"):
            subset = [
                row
                for row in diet_rows
                if row["Species"] == species and row["Diet"] == "PD"
            ]
            value = log_hazard_slope(subset)
            key = f"{species.casefold()}_pd_log_hazard_slope"
            hazard_values[key] = value
            expected[key] = (value, value, value)
        with (problem_root / "grip_strength.csv").open(newline="") as handle:
            grip_rows = list(csv.DictReader(handle))
        hecale_grip = individual_grip_slopes(grip_rows, "Hecale")
        dryas_grip = individual_grip_slopes(grip_rows, "Dryas")
        grip_contrast = statistics.median(hecale_grip) - statistics.median(dryas_grip)
        grip_samples: list[float] = []
        for _ in range(1000):
            sampled_hecale = [
                hecale_grip[rng.randrange(len(hecale_grip))]
                for _ in hecale_grip
            ]
            sampled_dryas = [
                dryas_grip[rng.randrange(len(dryas_grip))]
                for _ in dryas_grip
            ]
            grip_samples.append(
                statistics.median(sampled_hecale)
                - statistics.median(sampled_dryas)
            )
        expected["grip_age_slope_contrast"] = (
            grip_contrast,
            percentile(grip_samples, 0.025),
            percentile(grip_samples, 0.975),
        )
        submitted: dict[str, tuple[float, float, float]] = {}
        submitted_row_count = 0
        with metrics_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            if not {"metric", "estimate", "ci_lower", "ci_upper"}.issubset(
                set(reader.fieldnames or [])
            ):
                return f"{prefix} invalid metric schema."
            for row in reader:
                submitted_row_count += 1
                submitted[row["metric"]] = (
                    float(row["estimate"]),
                    float(row["ci_lower"]),
                    float(row["ci_upper"]),
                )
    except (OSError, ValueError, KeyError, csv.Error, ZeroDivisionError):
        return f"{prefix} could not validate submitted metrics."
    submission_shape_valid = (
        submitted_row_count == len(expected) and len(submitted) == len(expected)
    )
    matched = 0
    ci_matched = 0
    valid_intervals = 0
    for metric, expected_row in expected.items():
        row = submitted.get(metric)
        if row is None:
            continue
        value, expected_lower, expected_upper = expected_row
        estimate, lower, upper = row
        tolerance = max(1e-6, abs(value) * 1e-3)
        matched += abs(estimate - value) <= tolerance
        lower_tolerance = max(1e-6, abs(expected_lower) * 1e-3)
        upper_tolerance = max(1e-6, abs(expected_upper) * 1e-3)
        ci_matched += (
            abs(lower - expected_lower) <= lower_tolerance
            and abs(upper - expected_upper) <= upper_tolerance
        )
        valid_intervals += lower <= estimate <= upper
    if not submission_shape_valid:
        matched = 0
        ci_matched = 0
        valid_intervals = 0
    return (
        f"{prefix} matched={matched}/{len(expected)}; ci_matched={ci_matched}/"
        f"{len(expected)}; valid_intervals={valid_intervals}/"
        f"{len(expected)}; median_species_max_ratio={expected['median_species_max_ratio'][0]:.6g}; "
        f"maximum_lifespan_days={expected['maximum_verified_lifespan_days'][0]:.6g}; "
        f"hecale_PD_median={expected['hecale_pd_km_median_days'][0]:.6g}; "
        f"dryas_PD_median={expected['dryas_pd_km_median_days'][0]:.6g}; "
        f"hecale_PD_hazard_slope={hazard_values['hecale_pd_log_hazard_slope']:.6g}; "
        f"dryas_PD_hazard_slope={hazard_values['dryas_pd_log_hazard_slope']:.6g}; "
        f"grip_age_slope_contrast={grip_contrast:.6g}."
    )


def parse_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _normalized_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _quote_occurs(quote: str, text: str | None) -> bool:
    normalized_quote = _normalized_text(quote)
    return len(normalized_quote) >= 12 and normalized_quote in _normalized_text(text or "")


def _analysis_transcript(transcript: str | None) -> str:
    if not transcript:
        return ""
    return transcript.split("\n## Final Answer", 1)[0]


def _safe_artifact_path(root: Path | None, relative: str | None) -> Path | None:
    if root is None or not relative:
        return None
    try:
        candidate = (root / relative).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def _verify_citation(
    citation: EvidenceCitation,
    *,
    final_answer: str,
    transcript: str | None,
    artifact_root: Path | None,
) -> bool:
    if citation.source == "transcript":
        citation.verified = _quote_occurs(citation.quote, _analysis_transcript(transcript))
    elif citation.source == "final_answer":
        citation.verified = _quote_occurs(citation.quote, final_answer)
    else:
        artifact = _safe_artifact_path(artifact_root, citation.artifact_path)
        if artifact is None or artifact.stat().st_size > 10_000_000:
            citation.verified = False
        else:
            try:
                citation.verified = _quote_occurs(
                    citation.quote,
                    artifact.read_text(errors="replace"),
                )
            except OSError:
                citation.verified = False
    return citation.verified


def _transcript_for_judge(transcript: str | None) -> str | None:
    """Select evidence-bearing sections instead of blindly keeping the transcript tail."""
    if not transcript:
        return None
    max_chars = int(os.getenv("JUDGE_TRANSCRIPT_MAX_CHARS", "160000"))
    if len(transcript) <= max_chars:
        return transcript

    sections = re.split(r"(?=^## )", transcript, flags=re.MULTILINE)
    selected: list[str] = []
    used = 0
    priorities = ("## Tool:", "## Assistant Step", "## Task")
    for prefix in priorities:
        for section in sections:
            if not section.startswith(prefix):
                continue
            excerpt = section[:6000]
            if used + len(excerpt) > max_chars:
                continue
            selected.append(excerpt)
            used += len(excerpt)
    return (
        "[Structured transcript selection: tool outputs and analysis steps; "
        f"{len(transcript)} source characters]\n\n" + "\n".join(selected)
    )


def _verify_analysis_manifest(
    manifest_path: Path | None,
    artifact_root: Path | None,
) -> tuple[bool, list[str]]:
    if manifest_path is None:
        return False, ["No analysis manifest was submitted."]
    max_manifest_bytes = int(os.getenv("BIOEVAL_MAX_MANIFEST_BYTES", "1000000"))
    max_artifacts = int(os.getenv("BIOEVAL_MAX_ARTIFACT_COUNT", "100"))
    max_file_bytes = int(os.getenv("BIOEVAL_MAX_ARTIFACT_BYTES", "100000000"))
    max_total_bytes = int(os.getenv("BIOEVAL_MAX_ARTIFACT_TOTAL_BYTES", "500000000"))
    try:
        if manifest_path.stat().st_size > max_manifest_bytes:
            return False, ["Analysis manifest exceeds the size limit."]
        manifest = json.loads(manifest_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, [f"Analysis manifest could not be read: {exc}"]
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return False, ["Analysis manifest has no declared artifacts."]
    if len(artifacts) > max_artifacts:
        return False, ["Analysis manifest declares too many artifacts."]

    root = artifact_root or manifest_path.parent
    messages: list[str] = []
    valid = True
    seen_paths: set[str] = set()
    total_bytes = 0
    for item in artifacts:
        if not isinstance(item, dict):
            valid = False
            messages.append("Manifest contains a malformed artifact row.")
            continue
        relative = item.get("path")
        artifact = _safe_artifact_path(root, relative)
        if artifact is None:
            valid = False
            messages.append(f"Missing or unsafe artifact path: {relative!r}.")
            continue
        normalized = str(artifact.resolve().relative_to(root.resolve()))
        if normalized in seen_paths:
            valid = False
            messages.append(f"Duplicate artifact path: {relative}.")
            continue
        seen_paths.add(normalized)
        size = artifact.stat().st_size
        total_bytes += size
        if size > max_file_bytes:
            valid = False
            messages.append(f"Artifact exceeds the per-file size limit: {relative}.")
            continue
        if total_bytes > max_total_bytes:
            valid = False
            messages.append("Declared artifacts exceed the total size limit.")
            continue
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_hash
        ):
            valid = False
            messages.append(f"Missing or invalid SHA-256 for artifact: {relative}.")
            continue
        digest = hashlib.sha256()
        with artifact.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual_hash = digest.hexdigest()
        if actual_hash.casefold() != expected_hash.casefold():
            valid = False
            messages.append(f"SHA-256 mismatch for artifact: {relative}.")
    if valid:
        messages.append(f"Verified {len(artifacts)} declared artifact(s).")
    return valid, messages


def _artifact_evidence_for_judge(
    manifest_path: Path | None,
    artifact_root: Path | None,
) -> list[dict]:
    if manifest_path is None:
        return []
    try:
        manifest = json.loads(manifest_path.read_text(errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    root = artifact_root or manifest_path.parent
    evidence: list[dict] = []
    remaining = int(os.getenv("JUDGE_ARTIFACT_MAX_CHARS", "80000"))
    for item in manifest.get("artifacts", []):
        if not isinstance(item, dict):
            continue
        artifact = _safe_artifact_path(root, item.get("path"))
        if artifact is None or artifact.stat().st_size > 10_000_000 or remaining <= 0:
            continue
        try:
            text = artifact.read_text(errors="replace")
        except OSError:
            continue
        excerpt = text[: min(20_000, remaining)]
        remaining -= len(excerpt)
        evidence.append({"path": item.get("path"), "text_excerpt": excerpt})
    return evidence


def _deterministic_result(
    *,
    draft: dict,
    expected_conclusions: list[str],
    expected_caveats: list[str],
    final_answer: str,
    transcript: str | None,
    artifact_root: Path | None,
    manifest_verified: bool,
    manifest_messages: list[str],
) -> JudgeResult:
    validation = list(manifest_messages)
    raw_conclusion_rows = [
        row for row in draft.get("per_conclusion", []) if isinstance(row, dict)
    ]
    for expected in expected_conclusions:
        count = sum(row.get("conclusion") == expected for row in raw_conclusion_rows)
        if count != 1:
            validation.append(
                f"Expected exactly one conclusion row but received {count}: {expected}"
            )
    for row in raw_conclusion_rows:
        if row.get("conclusion") not in expected_conclusions:
            validation.append(
                f"Ignored unknown conclusion row: {row.get('conclusion')!r}"
            )
    raw_conclusions = {
        row.get("conclusion"): row
        for row in raw_conclusion_rows
        if isinstance(row.get("conclusion"), str)
    }
    per_conclusion: list[ConclusionScore] = []
    support_kinds = {"command_output", "data_excerpt", "analysis_result", "artifact"}
    for expected in expected_conclusions:
        raw = raw_conclusions.get(expected)
        score = (
            ConclusionScore.model_validate(raw)
            if raw is not None
            else ConclusionScore(conclusion=expected)
        )
        for citation in score.citations:
            _verify_citation(
                citation,
                final_answer=final_answer,
                transcript=transcript,
                artifact_root=artifact_root,
            )
        score.evidence_verified = any(
            citation.verified
            and citation.evidence_kind in support_kinds
            and citation.source in {"transcript", "artifact"}
            for citation in score.citations
        )
        if score.status in {"matched", "partial"} and not score.evidence_verified:
            validation.append(
                f"Downgraded unsupported conclusion to missing: {expected}"
            )
            score.status = "missing"
        per_conclusion.append(score)

    raw_caveat_rows = [
        row for row in draft.get("per_caveat", []) if isinstance(row, dict)
    ]
    for expected in expected_caveats:
        count = sum(row.get("caveat") == expected for row in raw_caveat_rows)
        if count != 1:
            validation.append(
                f"Expected exactly one caveat row but received {count}: {expected}"
            )
    for row in raw_caveat_rows:
        if row.get("caveat") not in expected_caveats:
            validation.append(f"Ignored unknown caveat row: {row.get('caveat')!r}")
    raw_caveats = {
        row.get("caveat"): row
        for row in raw_caveat_rows
        if isinstance(row.get("caveat"), str)
    }
    per_caveat: list[CaveatScore] = []
    for expected in expected_caveats:
        raw = raw_caveats.get(expected)
        score = (
            CaveatScore.model_validate(raw)
            if raw is not None
            else CaveatScore(caveat=expected)
        )
        for citation in score.citations:
            _verify_citation(
                citation,
                final_answer=final_answer,
                transcript=transcript,
                artifact_root=artifact_root,
            )
        score.evidence_verified = any(citation.verified for citation in score.citations)
        if score.status in {"addressed", "partial"} and not score.evidence_verified:
            validation.append(f"Downgraded unsupported caveat to missing: {expected}")
            score.status = "missing"
        per_caveat.append(score)

    conclusion_points = {"matched": 1.0, "partial": 0.5, "missing": 0.0, "wrong": 0.0}
    conclusion_score = (
        sum(conclusion_points[row.status] for row in per_conclusion) / len(per_conclusion)
        if per_conclusion
        else 0.0
    )
    caveat_points = {"addressed": 1.0, "partial": 0.5, "missing": 0.0}
    caveat_score = (
        sum(caveat_points[row.status] for row in per_caveat) / len(per_caveat)
        if per_caveat
        else 1.0
    )
    execution_score = 1.0 if manifest_verified else 0.0
    if per_caveat:
        overall = 0.75 * conclusion_score + 0.15 * caveat_score + 0.10 * execution_score
    else:
        overall = 0.90 * conclusion_score + 0.10 * execution_score

    leakage = bool(draft.get("leakage_suspected", False))
    if leakage:
        overall = min(overall, 0.25)
        verdict = "fail"
    elif overall >= 0.75:
        verdict = "pass"
    elif overall >= 0.50:
        verdict = "borderline"
    else:
        verdict = "fail"

    return JudgeResult(
        score=round(overall, 4),
        verdict=verdict,
        per_conclusion=per_conclusion,
        per_caveat=per_caveat,
        matched_conclusions=[
            row.conclusion for row in per_conclusion if row.status == "matched"
        ],
        missing_or_wrong=[
            row.conclusion
            for row in per_conclusion
            if row.status in {"missing", "wrong"}
        ],
        caveats_addressed=[
            row.caveat for row in per_caveat if row.status == "addressed"
        ],
        conclusion_score=round(conclusion_score, 4),
        caveat_score=round(caveat_score, 4),
        execution_score=execution_score,
        analysis_manifest_verified=manifest_verified,
        evidence_validation=validation,
        leakage_suspected=leakage,
        leakage_rationale=str(draft.get("leakage_rationale", "")),
        rationale=str(draft.get("rationale", "")),
    )


def _apply_forge_metric_gate(
    result: JudgeResult,
    evaluator_summary: str | None,
) -> JudgeResult:
    if not evaluator_summary:
        return result
    pattern = re.compile(
        r"coverage=(\d+)/(\d+); duplicates=(\d+); unknown_rows=(\d+); "
        r"baseline_RMSE=([0-9.eE+-]+); dependency_RMSE=([0-9.eE+-]+); "
        r"baseline_MAE=([0-9.eE+-]+); dependency_MAE=([0-9.eE+-]+); "
        r"frozen_RMSE=([0-9.eE+-]+); frozen_MAE=([0-9.eE+-]+)"
    )
    match = pattern.search(evaluator_summary)
    reasons: list[str] = []
    if match is None:
        reasons.append("FORGE hidden holdout metrics were unavailable or invalid.")
    else:
        covered, total, duplicates, unknown = map(int, match.group(1, 2, 3, 4))
        baseline_rmse, dependency_rmse, baseline_mae, dependency_mae = map(
            float,
            match.group(5, 6, 7, 8),
        )
        frozen_rmse, frozen_mae = map(float, match.group(9, 10))
        if total == 0 or covered / total < 0.95:
            reasons.append("FORGE held-out prediction coverage was below 95%.")
        if duplicates:
            reasons.append("FORGE predictions contained duplicate keys.")
        if unknown:
            reasons.append("FORGE predictions contained unknown held-out keys.")
        if not (
            dependency_rmse < baseline_rmse
            and dependency_mae <= baseline_mae
        ):
            reasons.append(
                "Dependency-informed predictions did not improve RMSE without degrading MAE."
            )
        if baseline_rmse > frozen_rmse or baseline_mae > frozen_mae * 1.05:
            reasons.append(
                "Submitted expression baseline underperformed the frozen training-only baseline."
            )
        direction = re.search(
            r"EGFR_erlotinib_n=(\d+); benefit_dependency_r=([0-9.eE+naN-]+); "
            r"benefit_IC50_r=([0-9.eE+naN-]+)",
            evaluator_summary,
        )
        if direction is None:
            reasons.append("EGFR-erlotinib benefit-score checks were unavailable.")
        else:
            n = int(direction.group(1))
            try:
                dependency_r = float(direction.group(2))
                ic50_r = float(direction.group(3))
            except ValueError:
                dependency_r = ic50_r = math.nan
            if (
                n < 10
                or not math.isfinite(dependency_r)
                or not math.isfinite(ic50_r)
                or dependency_r <= 0
                or ic50_r >= 0
            ):
                reasons.append(
                    "EGFR-erlotinib benefit scores failed the prespecified directionality gate."
                )
    if not reasons:
        return result
    result.execution_score = 0.0
    result.score = min(result.score, 0.49)
    result.verdict = "fail"
    result.evidence_validation.extend(reasons)
    return result


def _apply_idr_metric_gate(
    result: JudgeResult,
    evaluator_summary: str | None,
) -> JudgeResult:
    if not evaluator_summary:
        return result
    match = re.search(
        r"coverage=(\d+)/(\d+); duplicates=(\d+); unknown_rows=(\d+); "
        r"baseline_RMSE=([0-9.eE+-]+); model_RMSE=([0-9.eE+-]+)",
        evaluator_summary,
    )
    reasons: list[str] = []
    if match is None:
        reasons.append("IDR hidden perturbation metrics were unavailable or invalid.")
    else:
        covered, total, duplicates, unknown = map(int, match.group(1, 2, 3, 4))
        baseline_rmse, model_rmse = map(float, match.group(5, 6))
        if total == 0 or covered / total < 0.95:
            reasons.append("IDR held-out prediction coverage was below 95%.")
        if duplicates or unknown:
            reasons.append("IDR predictions contained duplicate or unknown keys.")
        if model_rmse >= baseline_rmse:
            reasons.append("IDR predictions did not improve on the training-mean baseline.")
    if reasons:
        result.execution_score = 0.0
        result.score = min(result.score, 0.49)
        result.verdict = "fail"
        result.evidence_validation.extend(reasons)
    return result


def _apply_f1_model_gate(
    result: JudgeResult,
    evaluator_summary: str | None,
) -> JudgeResult:
    match = re.search(
        r"three_fitted=(\d+); three_all_fail=(\d+); four_passing=(\d+); "
        r"four_minus_three_BIC=([0-9.eE+inf-]+); invalid_rows=(\d+)",
        evaluator_summary or "",
    )
    reasons: list[str] = [
        "F1 model predictions are not independently recomputed from the supplied observations."
    ]
    if match is None:
        reasons.append("F1 deterministic model-selection evidence was unavailable.")
    else:
        three, three_fail, four, invalid = map(
            int,
            (match.group(1), match.group(2), match.group(3), match.group(5)),
        )
        bic_delta = float(match.group(4))
        if three < 1 or three_fail != 1:
            reasons.append("No adequately fitted three-conformation class failed validation.")
        if four < 1:
            reasons.append("No four-conformation model passed all fixed constraints.")
        if not math.isfinite(bic_delta) or bic_delta > 10:
            reasons.append("The four-conformation model failed the fixed BIC penalty.")
        if invalid:
            reasons.append("F1 model-summary rows failed deterministic consistency checks.")
    if reasons:
        result.execution_score = 0.0
        result.score = min(result.score, 0.49)
        result.verdict = "fail"
        result.evidence_validation.extend(reasons)
    return result


def _apply_butterfly_metric_gate(
    result: JudgeResult,
    evaluator_summary: str | None,
) -> JudgeResult:
    match = re.search(
        r"matched=(\d+)/(\d+); ci_matched=(\d+)/(\d+); "
        r"valid_intervals=(\d+)/(\d+); "
        r"median_species_max_ratio=([0-9.eE+-]+); "
        r"maximum_lifespan_days=([0-9.eE+-]+); "
        r"hecale_PD_median=([0-9.eE+-]+); dryas_PD_median=([0-9.eE+-]+); "
        r"hecale_PD_hazard_slope=([0-9.eE+-]+); "
        r"dryas_PD_hazard_slope=([0-9.eE+-]+); "
        r"grip_age_slope_contrast=([0-9.eE+-]+)\.",
        evaluator_summary or "",
    )
    reasons: list[str] = []
    if match is None:
        reasons.append("Butterfly deterministic survival metrics were unavailable.")
    else:
        matched, total, ci_matched, ci_total, intervals, interval_total = map(
            int, match.group(1, 2, 3, 4, 5, 6)
        )
        ratio, maximum, hecale_pd, dryas_pd, hecale_hazard, dryas_hazard, grip = map(
            float, match.group(7, 8, 9, 10, 11, 12, 13)
        )
        if (
            matched != total
            or ci_matched != ci_total
            or intervals != interval_total
            or total != 9
        ):
            reasons.append("Submitted butterfly estimates or intervals failed verification.")
        if not 2.5 <= ratio <= 4.0 or maximum < 330:
            reasons.append("Species lifespan effects failed the prespecified numeric bounds.")
        if hecale_pd <= dryas_pd:
            reasons.append("Pollen-deprived Heliconius did not outlive the comparison species.")
        if hecale_hazard >= dryas_hazard:
            reasons.append("Butterfly actuarial-ageing direction failed verification.")
        if grip <= 0:
            reasons.append("Butterfly grip-ageing direction failed verification.")
    if reasons:
        result.execution_score = 0.0
        result.score = min(result.score, 0.49)
        result.verdict = "fail"
        result.evidence_validation.extend(reasons)
    return result


def judge_with_llm(
    *,
    problem_id: str,
    final_answer: str,
    transcript: str | None,
    model: str,
    api_base: str,
    log_dir: Path | None = None,
    analysis_manifest: Path | None = None,
    artifact_root: Path | None = None,
    allow_conditional: bool = False,
) -> JudgeResult:
    ensure_bedrock_bearer_token()
    if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK") and not os.environ.get("AWS_PROFILE"):
        raise RuntimeError(
            "Bedrock credentials required for judging. Set AWS_BEARER_TOKEN_BEDROCK or "
            "an ABSK... aws_session_token in ~/.aws/credentials."
        )

    spec = load_problem_spec(problem_id)
    if spec.benchmark_status == "acquisition_only":
        raise ValueError(f"{problem_id} is acquisition-only and cannot be judged.")
    if spec.benchmark_status == "conditional" and not allow_conditional:
        raise ValueError(
            f"{problem_id} is conditional; explicit judge approval is required."
        )
    manifest_verified, manifest_messages = _verify_analysis_manifest(
        analysis_manifest,
        artifact_root,
    )
    registered_evaluator = evaluate_problem_artifacts(
        problem_id,
        analysis_manifest,
        artifact_root,
        manifest_verified,
    )
    forge_summary = _forge_hidden_holdout_summary(
        problem_id=problem_id,
        manifest_path=analysis_manifest,
        artifact_root=artifact_root,
        manifest_verified=manifest_verified,
    )
    idr_summary = _idr_hidden_holdout_summary(
        problem_id=problem_id,
        manifest_path=analysis_manifest,
        artifact_root=artifact_root,
        manifest_verified=manifest_verified,
    )
    f1_summary = _f1_model_selection_summary(
        problem_id=problem_id,
        manifest_path=analysis_manifest,
        artifact_root=artifact_root,
        manifest_verified=manifest_verified,
    )
    butterfly_summary = _butterfly_survival_summary(
        problem_id=problem_id,
        manifest_path=analysis_manifest,
        artifact_root=artifact_root,
        manifest_verified=manifest_verified,
    )
    evaluator_summaries = [
        summary
        for summary in (
            registered_evaluator.summary if registered_evaluator else None,
            forge_summary,
            idr_summary,
            f1_summary,
            butterfly_summary,
        )
        if summary
    ]
    evaluator_summary = {
        FORGE_PROBLEM_ID: forge_summary,
        IDR_PROBLEM_ID: idr_summary,
        F1_PROBLEM_ID: f1_summary,
        BUTTERFLY_PROBLEM_ID: butterfly_summary,
    }.get(
        problem_id,
        registered_evaluator.summary if registered_evaluator else None,
    )
    judge_transcript = transcript
    if evaluator_summaries:
        judge_transcript = "\n".join(
            part for part in (transcript, *evaluator_summaries) if part
        )
    user_payload = {
        "task": "anonymized_biology_discovery_task",
        "output_schema": JUDGE_JSON_SCHEMA,
        "hidden_expected_conclusions": spec.expected_conclusions,
        "hidden_expected_caveats": spec.expected_caveats,
        "hidden_judge_rubric": spec.judge_rubric,
        "hidden_leak_markers": [spec.title, spec.doi, *spec.leak_markers],
        "uea_final_answer": final_answer,
        "uea_transcript_evidence": _transcript_for_judge(judge_transcript),
        "submitted_analysis_manifest": (
            read_optional(analysis_manifest) if analysis_manifest else None
        ),
        "submitted_artifact_excerpts": _artifact_evidence_for_judge(
            analysis_manifest,
            artifact_root,
        ),
    }

    client = create_bedrock_client(api_base)
    system_blocks = [{"text": JUDGE_SYSTEM_PROMPT}]
    cache_point = prompt_cache_point()
    if cache_point:
        system_blocks.append(cache_point)

    messages = messages_with_cache_point(
        [{"role": "user", "content": [{"text": json.dumps(user_payload)}]}],
        cache_point,
    )

    cost_tracker = BedrockCostTracker(component="judge", model=model, log_dir=log_dir)
    response = client.converse(
        modelId=model.removeprefix("bedrock/"),
        system=system_blocks,
        messages=messages,
        inferenceConfig={
            "maxTokens": int(os.getenv("JUDGE_MAX_TOKENS", "8192")),
            "temperature": float(os.getenv("JUDGE_TEMPERATURE", "0")),
        },
    )
    cost_tracker.record(response.get("usage", {}) or {})
    cost_tracker.finalize()

    text = extract_text_from_response(response)
    draft = parse_json_object(text)
    artifact_evidence = _artifact_evidence_for_judge(analysis_manifest, artifact_root)
    deterministic_leak_text = "\n".join(
        [
            final_answer,
            transcript or "",
            *[str(item.get("text_excerpt") or "") for item in artifact_evidence],
        ]
    )
    leak_markers = [spec.title, spec.doi, *spec.leak_markers]
    if contains_hidden_identifier(deterministic_leak_text, leak_markers):
        draft["leakage_suspected"] = True
        rationale = str(draft.get("leakage_rationale", "")).strip()
        deterministic = "Deterministic scan found a hidden target identifier."
        draft["leakage_rationale"] = (
            f"{rationale} {deterministic}".strip() if rationale else deterministic
        )
    result = _deterministic_result(
        draft=draft,
        expected_conclusions=spec.expected_conclusions,
        expected_caveats=spec.expected_caveats,
        final_answer=final_answer,
        transcript=judge_transcript,
        artifact_root=artifact_root or (analysis_manifest.parent if analysis_manifest else None),
        manifest_verified=manifest_verified,
        manifest_messages=manifest_messages,
    )
    if problem_id == FORGE_PROBLEM_ID:
        result = _apply_forge_metric_gate(result, evaluator_summary)
    elif problem_id == IDR_PROBLEM_ID:
        result = _apply_idr_metric_gate(result, evaluator_summary)
    elif problem_id == F1_PROBLEM_ID:
        result = _apply_f1_model_gate(result, evaluator_summary)
    elif problem_id == BUTTERFLY_PROBLEM_ID:
        result = _apply_butterfly_metric_gate(result, evaluator_summary)
    special_evaluators = {
        FORGE_PROBLEM_ID,
        IDR_PROBLEM_ID,
        F1_PROBLEM_ID,
        BUTTERFLY_PROBLEM_ID,
    }
    if (
        spec.benchmark_status in {"active", "conditional"}
        and registered_evaluator is None
        and problem_id not in special_evaluators
    ):
        result.execution_score = 0.0
        result.score = min(result.score, 0.49)
        result.verdict = "fail"
        result.evidence_validation.append(
            "Runnable problem has no deterministic scientific evaluator."
        )
    return apply_evaluator_gate(result, registered_evaluator)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judge a UEA answer against hidden paper conclusions.")
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--final-answer-file", type=Path, required=True)
    parser.add_argument("--transcript-file", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    parser.add_argument(
        "--api-base",
        default=os.getenv("JUDGE_API_BASE", DEFAULT_BEDROCK_API_BASE),
    )
    parser.add_argument("--run-id", default=os.getenv("BIOEVAL_RUN_ID"))
    parser.add_argument("--allow-conditional", action="store_true")
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--score-log", type=Path)
    parser.add_argument(
        "--analysis-manifest",
        type=Path,
        help=(
            "JSON manifest of submitted artifacts. Defaults to analysis_manifest.json "
            "beside the final answer when present."
        ),
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        help="Root directory for relative paths in the analysis manifest.",
    )
    return parser


def main() -> None:
    load_dotenv()
    args = build_arg_parser().parse_args()
    output_file = args.output_file or (args.final_answer_file.parent / "judge_result.json")
    log_dir = output_file.parent.parent / "logs" if output_file.parent.name == "results" else output_file.parent
    default_manifest = args.final_answer_file.parent / "analysis_manifest.json"
    analysis_manifest = args.analysis_manifest or (
        default_manifest if default_manifest.exists() else None
    )
    artifact_root = args.artifact_root or (
        analysis_manifest.parent if analysis_manifest else args.final_answer_file.parent
    )

    result = judge_with_llm(
        problem_id=args.problem_id,
        final_answer=args.final_answer_file.read_text(errors="replace"),
        transcript=read_optional(args.transcript_file),
        model=args.model,
        api_base=args.api_base,
        log_dir=log_dir,
        analysis_manifest=analysis_manifest,
        artifact_root=artifact_root,
        allow_conditional=args.allow_conditional,
    )
    result_dict = result.model_dump()
    record = {
        "event": "judge_result",
        "timestamp": utc_now(),
        "run_id": args.run_id,
        "problem_id": args.problem_id,
        "judge_model": args.model,
        "judge_api_base": args.api_base,
        "final_answer_file": str(args.final_answer_file),
        "transcript_file": str(args.transcript_file),
        "analysis_manifest": str(analysis_manifest) if analysis_manifest else None,
        "artifact_root": str(artifact_root),
        "result": result_dict,
    }

    score_log = args.score_log or (args.final_answer_file.parent / "score_history.jsonl")
    write_json(output_file, record)
    append_jsonl(score_log, record)
    print(json.dumps(result_dict, indent=2))
    print(f"Saved judge result to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
