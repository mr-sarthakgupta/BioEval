from __future__ import annotations

import hashlib
import csv
import json
import tempfile
import unittest
from pathlib import Path

from bioeval.judge import (
    FORGE_PROBLEM_ID,
    _deterministic_result,
    _forge_hidden_holdout_summary,
    _verify_analysis_manifest,
)


class JudgeScoringTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
