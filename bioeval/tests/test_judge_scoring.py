from __future__ import annotations

import hashlib
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bioeval.evaluators import evaluate_problem_artifacts
from bioeval.evaluators.biology import _MrcMap
from bioeval.evaluators.registry import _load_rules
from bioeval.judge import (
    BUTTERFLY_PROBLEM_ID,
    FORGE_PROBLEM_ID,
    _apply_butterfly_metric_gate,
    _butterfly_survival_summary,
    _deterministic_result,
    _forge_hidden_holdout_summary,
    _verify_analysis_manifest,
)
from bioeval.problems import load_problem_spec


class JudgeScoringTests(unittest.TestCase):
    def test_butterfly_metrics_recompute_ageing_and_intervals(self) -> None:
        rows = [
            ("median_species_max_ratio", 3.3047619047619046, 1.814207650273224, 6.103448275862069),
            ("maximum_verified_lifespan_days", 348, 348, 348),
            ("hecale_pf_km_median_days", 63, 52, 78),
            ("hecale_pd_km_median_days", 47, 38, 59),
            ("dryas_pf_km_median_days", 27, 22, 29),
            ("dryas_pd_km_median_days", 29, 23, 32),
            ("hecale_pd_log_hazard_slope", 0.056839152540220185, 0.056839152540220185, 0.056839152540220185),
            ("dryas_pd_log_hazard_slope", 0.11968719389194762, 0.11968719389194762, 0.11968719389194762),
            ("grip_age_slope_contrast", 0.0615, -0.081, 0.177),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics = root / "butterfly_metrics.csv"
            with metrics.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["metric", "estimate", "ci_lower", "ci_upper"])
                writer.writerows(rows)
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps({"artifacts": [{"path": metrics.name}]}),
                encoding="utf-8",
            )
            summary = _butterfly_survival_summary(
                problem_id=BUTTERFLY_PROBLEM_ID,
                manifest_path=manifest,
                artifact_root=root,
                manifest_verified=True,
            )
            self.assertIn("matched=9/9; ci_matched=9/9", summary or "")
            result = _deterministic_result(
                draft={
                    "conclusion_scores": [],
                    "caveat_scores": [],
                    "overall_feedback": "",
                    "leakage_suspected": False,
                    "leakage_rationale": "",
                },
                expected_conclusions=[],
                expected_caveats=[],
                final_answer="",
                transcript=None,
                artifact_root=root,
                manifest_verified=True,
                manifest_messages=[],
            )
            result.verdict = "pass"
            result.score = 1.0
            result.execution_score = 1.0
            gated = _apply_butterfly_metric_gate(result, summary)
            self.assertNotEqual(gated.verdict, "fail")
            rows[0] = (rows[0][0], rows[0][1], 0, 0)
            with metrics.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["metric", "estimate", "ci_lower", "ci_upper"])
                writer.writerows(rows)
            bad_summary = _butterfly_survival_summary(
                problem_id=BUTTERFLY_PROBLEM_ID,
                manifest_path=manifest,
                artifact_root=root,
                manifest_verified=True,
            )
            self.assertIn("ci_matched=8/9", bad_summary or "")

    def test_malformed_artifact_rules_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evaluator = root / "evaluator"
            evaluator.mkdir()
            (evaluator / "artifact_rules.json").write_text("{not-json")
            with patch(
                "bioeval.evaluators.registry._problem_root",
                return_value=root,
            ):
                rules = _load_rules("test-problem")
            self.assertIn("_load_error", rules)

    def test_new_biology_contracts_reject_malformed_artifacts(self) -> None:
        problem_ids = (
            "s41586-019-0933-9_mouse-gastrulation",
            "s41586-025-08855-w_rna-hydration",
            "s41586-023-06344-6_global-river-methane",
        )
        for problem_id in problem_ids:
            with self.subTest(problem_id=problem_id), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                artifact_entries = []
                for contract in load_problem_spec(problem_id).required_artifacts:
                    artifact = root / contract.path
                    with artifact.open("w", newline="") as handle:
                        writer = csv.DictWriter(handle, fieldnames=contract.columns)
                        writer.writeheader()
                        writer.writerows(
                            {column: "0" for column in contract.columns}
                            for _ in range(contract.min_rows)
                        )
                    artifact_entries.append({"path": contract.path})
                manifest = root / "analysis_manifest.json"
                manifest.write_text(json.dumps({"artifacts": artifact_entries}))

                output = evaluate_problem_artifacts(
                    problem_id,
                    manifest,
                    root,
                    True,
                )
                assert output is not None
                self.assertTrue(output.failures)

    def test_river_evaluator_recomputes_frozen_observation_summaries(self) -> None:
        problem_id = "s41586-023-06344-6_global-river-methane"
        rows = [
            {
                "dataset": "concentration",
                "positive_rows": 23218,
                "source_count": 246,
                "q10": 0.016705726000000004,
                "median": 0.2,
                "q90": 1.8015192934999984,
            },
            {
                "dataset": "measured_diffusive_flux",
                "positive_rows": 1721,
                "source_count": 68,
                "q10": 0.075201331,
                "median": 1.08,
                "q90": 16.47377856,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "observation_summary.csv"
            with summary.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps({"artifacts": [{"path": summary.name}]}),
                encoding="utf-8",
            )

            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertEqual(output.failures, [])

            rows[0]["median"] = 999
            with summary.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertTrue(
                any("concentration.median" in item for item in output.failures)
            )

            rows[0]["median"] = 0.2
            with summary.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows([*rows, rows[0]])
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertTrue(
                any("exactly one row" in item for item in output.failures)
            )

    def test_gastrulation_evaluator_scores_frozen_expression_holdout(self) -> None:
        problem_id = "s41586-019-0933-9_mouse-gastrulation"
        problem_root = Path(__file__).resolve().parents[2] / "problems_imcomplete" / problem_id
        with (
            problem_root / "evaluator" / "trajectory_holdout_labels.csv"
        ).open(newline="") as handle:
            labels = list(csv.DictReader(handle))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predictions = root / "trajectory_holdout.csv"
            with predictions.open("w", newline="") as handle:
                fields = [
                    "cell_id",
                    "predicted_time",
                    "confidence",
                ]
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for row in labels:
                    observed = float(row["observed_time"])
                    writer.writerow(
                        {
                            "cell_id": row["cell_id"],
                            "predicted_time": observed,
                            "confidence": 0.9,
                        }
                    )
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {"path": predictions.name},
                        ]
                    }
                )
            )
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertEqual(output.failures, [])
            self.assertIn("RMSE=0", output.summary)
            with predictions.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            rows[0]["cell_id"] = "invented_cell"
            with predictions.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertTrue(any("unknown cell" in item for item in output.failures))

    def test_gastrulation_mean_time_shortcut_fails_strong_baseline(self) -> None:
        problem_id = "s41586-019-0933-9_mouse-gastrulation"
        problem_root = (
            Path(__file__).resolve().parents[2] / "problems_imcomplete" / problem_id
        )
        with (
            problem_root / "evaluator" / "trajectory_holdout_labels.csv"
        ).open(newline="") as handle:
            labels = list(csv.DictReader(handle))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predictions = root / "trajectory_holdout.csv"
            with predictions.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("cell_id", "predicted_time", "confidence"))
                writer.writerows(
                    (row["cell_id"], 7.55, 0.5) for row in labels
                )
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps({"artifacts": [{"path": predictions.name}]})
            )
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertTrue(
                any("frozen expression baseline" in item for item in output.failures)
            )

    def test_rna_evaluator_recomputes_half_map_density(self) -> None:
        problem_id = "s41586-025-08855-w_rna-hydration"
        problem_root = Path(__file__).resolve().parents[2] / "problems_imcomplete" / problem_id
        with (problem_root / "evaluator" / "density_sites_fixture.csv").open(
            newline=""
        ) as handle:
            density_sites = list(csv.DictReader(handle))
        with (problem_root / "curated" / "map_manifest.csv").open(newline="") as handle:
            map_manifest = {
                (row["map_blind_id"], row["half_id"]): row
                for row in csv.DictReader(handle)
            }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parameters = root / "analysis_parameters.csv"
            with parameters.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(("parameter", "value"))
                writer.writerows(
                    (
                        ("coordinate_frame", "map_angstrom"),
                        ("minimum_peak_sigma", "3.0"),
                        ("replication_radius_angstrom", "1.5"),
                    )
                )
            parameter_hash = hashlib.sha256(parameters.read_bytes()).hexdigest()
            calls = root / "hydration_calls.csv"
            fields = load_problem_spec(problem_id).required_artifacts[0].columns
            maps = {
                key: _MrcMap(
                    problem_root / "data" / "half-maps" / row["filename"]
                )
                for key, row in map_manifest.items()
            }
            with calls.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for map_id in ("map_a", "map_b"):
                    for site in density_sites:
                        point = tuple(
                            float(site[column])
                            for column in ("x_angstrom", "y_angstrom", "z_angstrom")
                        )
                        for half_id in ("1", "2"):
                            map_row = map_manifest[(map_id, half_id)]
                            writer.writerow(
                                {
                                    "schema_version": "1.0",
                                    "run_id": "fixture",
                                    "site_id": site["site_id"],
                                    "map_blind_id": map_id,
                                    "half_id": half_id,
                                    "x_angstrom": site["x_angstrom"],
                                    "y_angstrom": site["y_angstrom"],
                                    "z_angstrom": site["z_angstrom"],
                                    "peak_sigma": maps[(map_id, half_id)].peak_sigma(
                                        point
                                    ),
                                    "confidence": 0.9,
                                    "input_sha256": map_row["sha256"],
                                    "parameter_sha256": parameter_hash,
                                }
                            )
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {"path": calls.name},
                            {"path": parameters.name},
                        ]
                    }
                )
            )
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertEqual(output.failures, [])
            self.assertIn("density_valid=24", output.summary)
            with calls.open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            duplicate_rows = []
            for map_id in ("map_a", "map_b"):
                source_rows = [
                    row
                    for row in rows
                    if row["map_blind_id"] == map_id
                    and row["site_id"] == density_sites[0]["site_id"]
                ]
                for index in range(5):
                    duplicate_rows.extend(
                        [{**row, "site_id": f"duplicate_{index}"} for row in source_rows]
                    )
            with calls.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(duplicate_rows)
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertTrue(
                any("same spatial peak" in item for item in output.failures)
            )

            for row in rows:
                row["x_angstrom"] = str(float(row["x_angstrom"]) + 20)
            with calls.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            output = evaluate_problem_artifacts(
                problem_id, manifest, root, True
            )
            assert output is not None
            self.assertTrue(
                any(
                    "density" in item.lower() or "half-map" in item.lower()
                    for item in output.failures
                )
            )

    def test_human_mass_has_no_runnable_evaluator_while_acquisition_only(self) -> None:
        problem_id = "s41586-020-3010-5_human-made-mass"
        self.assertIsNone(
            evaluate_problem_artifacts(problem_id, None, None, False)
        )

    def test_forge_predictions_are_scored_against_hidden_labels(self) -> None:
        labels_path = (
            Path(__file__).resolve().parents[2]
            / "problems_complete"
            / FORGE_PROBLEM_ID
            / "evaluator"
            / "drug_response_test_labels.csv"
        )
        with labels_path.open(newline="") as handle:
            label = next(csv.DictReader(handle))
        observed = float(label["observed_ic50"])

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predictions = root / "forge_predictions.csv"
            with predictions.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "drug",
                        "cell_line_id",
                        "baseline_prediction",
                        "dependency_informed_prediction",
                        "therapeutic_benefit_score",
                    ]
                )
                writer.writerow(
                    [
                        label["drug"],
                        label["cell_line_id"],
                        observed + 2,
                        observed + 1,
                        0,
                    ]
                )
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "path": predictions.name,
                                "sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
                            }
                        ]
                    }
                )
            )
            summary = _forge_hidden_holdout_summary(
                problem_id=FORGE_PROBLEM_ID,
                manifest_path=manifest,
                artifact_root=root,
                manifest_verified=True,
            )

        assert summary is not None
        self.assertIn("coverage=1/", summary)
        self.assertIn("baseline_RMSE=2", summary)
        self.assertIn("dependency_RMSE=1", summary)

    def test_score_is_derived_and_unsupported_claims_receive_no_credit(self) -> None:
        conclusion_a = "Species A lives longer than species B."
        conclusion_b = "The treatment causes the difference."
        caveat = "The observational comparison is sample-size sensitive."
        transcript = "Tool output: median survival ratio = 3.1 for A versus B."
        final_answer = (
            "Species A lives longer. The observational comparison is sample-size sensitive."
        )
        draft = {
            "per_conclusion": [
                {
                    "conclusion": conclusion_a,
                    "status": "matched",
                    "evidence": "Computed from survival data.",
                    "citations": [
                        {
                            "source": "transcript",
                            "evidence_kind": "analysis_result",
                            "quote": "median survival ratio = 3.1 for A versus B",
                            "artifact_path": None,
                        }
                    ],
                },
                {
                    "conclusion": conclusion_b,
                    "status": "matched",
                    "evidence": "Asserted without analysis.",
                    "citations": [],
                },
            ],
            "per_caveat": [
                {
                    "caveat": caveat,
                    "status": "addressed",
                    "citations": [
                        {
                            "source": "final_answer",
                            "evidence_kind": "final_claim",
                            "quote": "observational comparison is sample-size sensitive",
                            "artifact_path": None,
                        }
                    ],
                }
            ],
            "leakage_suspected": False,
            "leakage_rationale": "",
            "rationale": "One supported and one unsupported conclusion.",
        }

        result = _deterministic_result(
            draft=draft,
            expected_conclusions=[conclusion_a, conclusion_b],
            expected_caveats=[caveat],
            final_answer=final_answer,
            transcript=transcript,
            artifact_root=None,
            manifest_verified=True,
            manifest_messages=["Verified manifest."],
        )

        self.assertEqual(result.per_conclusion[0].status, "matched")
        self.assertTrue(result.per_conclusion[0].evidence_verified)
        self.assertEqual(result.per_conclusion[1].status, "missing")
        self.assertEqual(result.conclusion_score, 0.5)
        self.assertEqual(result.score, 0.625)
        self.assertEqual(result.verdict, "borderline")

    def test_leakage_is_a_deterministic_failure_cap(self) -> None:
        conclusion = "A supported conclusion."
        draft = {
            "per_conclusion": [
                {
                    "conclusion": conclusion,
                    "status": "matched",
                    "evidence": "Supported.",
                    "citations": [
                        {
                            "source": "transcript",
                            "evidence_kind": "command_output",
                            "quote": "measured effect size was 4.2 units",
                            "artifact_path": None,
                        }
                    ],
                }
            ],
            "per_caveat": [],
            "leakage_suspected": True,
            "leakage_rationale": "Exact hidden DOI appeared.",
            "rationale": "",
        }

        result = _deterministic_result(
            draft=draft,
            expected_conclusions=[conclusion],
            expected_caveats=[],
            final_answer="",
            transcript="Command output: measured effect size was 4.2 units.",
            artifact_root=None,
            manifest_verified=True,
            manifest_messages=[],
        )

        self.assertEqual(result.score, 0.25)
        self.assertEqual(result.verdict, "fail")

    def test_manifest_verifies_paths_and_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = root / "analysis.txt"
            artifact.write_text("analysis output")
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "path": "analysis.txt",
                                "sha256": digest,
                                "description": "Primary analysis output",
                            }
                        ]
                    }
                )
            )

            verified, messages = _verify_analysis_manifest(manifest, root)

            self.assertTrue(verified)
            self.assertIn("Verified 1 declared artifact(s).", messages)

            manifest.write_text(
                json.dumps({"artifacts": [{"path": "analysis.txt"}]})
            )
            verified, messages = _verify_analysis_manifest(manifest, root)
            self.assertFalse(verified)
            self.assertTrue(any("Missing or invalid SHA-256" in item for item in messages))

            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {"path": "analysis.txt", "sha256": digest},
                            {"path": "analysis.txt", "sha256": digest},
                        ]
                    }
                )
            )
            verified, messages = _verify_analysis_manifest(manifest, root)
            self.assertFalse(verified)
            self.assertTrue(any("Duplicate artifact path" in item for item in messages))


if __name__ == "__main__":
    unittest.main()
