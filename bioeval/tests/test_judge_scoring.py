from __future__ import annotations

import hashlib
import csv
import gzip
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
        problem_root = Path(__file__).resolve().parents[2] / "problems_complete" / problem_id
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
            Path(__file__).resolve().parents[2] / "problems_complete" / problem_id
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
        problem_root = Path(__file__).resolve().parents[2] / "problems_complete" / problem_id
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

    def test_human_mass_evaluator_recomputes_bounded_accounting(self) -> None:
        problem_id = "s41586-020-3010-5_human-made-mass"
        problem_root = (
            Path(__file__).resolve().parents[2]
            / "problems_complete"
            / problem_id
        )
        with (
            problem_root / "curated" / "annual_material_stocks_1900_2015.csv"
        ).open(newline="") as handle:
            material = {
                int(row["year"]): row
                for row in csv.DictReader(handle)
            }
        with (
            problem_root / "curated" / "historical_biomass_estimates_pre2016.csv"
        ).open(newline="") as handle:
            biomass = [
                row
                for row in csv.DictReader(handle)
                if row["observation_year"] == "2010"
            ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            material_output = root / "material_stock_summary.csv"
            with material_output.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    ["accounting_definition", "anchor_year", "total_teratonnes"]
                )
                for year in (1900, 1950, 1980, 2000, 2010, 2015):
                    row = material[year]
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
                    writer.writerow(["in_use_only", year, in_use])
                    writer.writerow(
                        ["in_use_plus_waste", year, in_use + float(row["waste_tt"])]
                    )
            biomass_output = root / "biomass_envelope.csv"
            with biomass_output.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "source_group",
                        "observation_year",
                        "biomass_gt_carbon",
                        "biomass_dry_min_gt",
                        "biomass_dry_max_gt",
                    ]
                )
                for row in biomass:
                    carbon = float(row["biomass_gt_carbon"])
                    writer.writerow(
                        [row["source_group"], 2010, carbon, carbon * 1.8, carbon * 2.2]
                    )
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {"path": material_output.name},
                            {"path": biomass_output.name},
                        ]
                    }
                ),
                encoding="utf-8",
            )
            output = evaluate_problem_artifacts(problem_id, manifest, root, True)
            assert output is not None
            self.assertEqual(output.failures, [])
            with material_output.open(newline="") as handle:
                rows = list(csv.reader(handle))
            rows[1][2] = str(float(rows[1][2]) + 1)
            with material_output.open("w", newline="") as handle:
                csv.writer(handle).writerows(rows)
            output = evaluate_problem_artifacts(problem_id, manifest, root, True)
            assert output is not None
            self.assertTrue(
                any("not recomputed" in failure for failure in output.failures)
            )

    def test_chromatin_evaluator_recomputes_pilot_bins(self) -> None:
        problem_id = "nature09906_chromatin-state-dynamics"
        problem_root = (
            Path(__file__).resolve().parents[2]
            / "problems_complete"
            / problem_id
        )
        with (problem_root / "curated" / "pilot_track_map.csv").open(
            newline=""
        ) as handle:
            tracks = list(csv.DictReader(handle))
        counts: dict[str, dict[tuple[str, int], int]] = {}
        totals: dict[str, int] = {}
        for track in tracks:
            track_counts: dict[tuple[str, int], int] = {}
            total = 0
            path = (
                problem_root
                / "data"
                / "pilot-h1-k562-chr21-chr22"
                / track["filename"]
            )
            with gzip.open(path, "rt", errors="replace") as handle:
                for line in handle:
                    fields = line.split("\t", 3)
                    midpoint = (int(fields[1]) + int(fields[2])) // 2
                    key = (fields[0], midpoint // 1_000_000 * 1_000_000)
                    track_counts[key] = track_counts.get(key, 0) + 1
                    total += 1
            counts[track["track_id"]] = track_counts
            totals[track["track_id"]] = total

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "chromatin_bin_summary.csv"
            with summary.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "cell_type",
                        "chromosome",
                        "bin_start",
                        "mark",
                        "mark_rpm",
                        "control_rpm",
                        "log2_enrichment",
                    ]
                )
                for cell_type in ("H1", "K562"):
                    control_id = f"{cell_type}_WCE"
                    for mark in ("H3K27me3", "H3K4me3"):
                        mark_id = f"{cell_type}_{mark}"
                        keys = sorted(set(counts[mark_id]) | set(counts[control_id]))
                        for chromosome, bin_start in keys:
                            mark_rpm = counts[mark_id].get(
                                (chromosome, bin_start), 0
                            ) * (1_000_000 / totals[mark_id])
                            control_rpm = counts[control_id].get(
                                (chromosome, bin_start), 0
                            ) * (1_000_000 / totals[control_id])
                            writer.writerow(
                                [
                                    cell_type,
                                    chromosome,
                                    bin_start,
                                    mark,
                                    mark_rpm,
                                    control_rpm,
                                    math.log2(
                                        (mark_rpm + 1.0) / (control_rpm + 1.0)
                                    ),
                                ]
                            )
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps({"artifacts": [{"path": summary.name}]}),
                encoding="utf-8",
            )
            output = evaluate_problem_artifacts(problem_id, manifest, root, True)
            assert output is not None
            self.assertEqual(output.failures, [])
            self.assertIn("mismatches=0", output.summary)

    def test_f1_observation_evaluator_recomputes_all_datasets(self) -> None:
        problem_id = "s41467-026-73844-0_f1-atpase-markov-model"
        rows = [
            ("turnover", 4, 1e-6, 1e-3, 1.951, 76.92, 1.0),
            ("coupling", 4, 1e-6, 1e-3, 1.0, 1.0, 0.0),
            (
                "atp_binding",
                15,
                1.202264434617413e-8,
                0.0020417379446695297,
                0.57,
                3.0,
                0.9857142857142858,
            ),
            (
                "adp_binding",
                15,
                3.981071705534969e-8,
                0.0020417379446695297,
                0.51,
                3.0,
                0.9964285714285714,
            ),
            (
                "mixed_binding",
                16,
                1.1748975549395302e-8,
                0.0020417379446695297,
                0.54,
                2.94,
                0.9948494231218898,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "f1_observation_summary.csv"
            with summary.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "dataset",
                        "observation_count",
                        "min_concentration_molar",
                        "max_concentration_molar",
                        "min_observed_value",
                        "max_observed_value",
                        "spearman_concentration_value",
                    ]
                )
                writer.writerows(rows)
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps({"artifacts": [{"path": summary.name}]}),
                encoding="utf-8",
            )
            output = evaluate_problem_artifacts(problem_id, manifest, root, True)
            assert output is not None
            self.assertEqual(output.failures, [])
            self.assertIn("mismatches=0", output.summary)

    def test_protein_resistance_evaluator_recomputes_fold0_pilot(self) -> None:
        problem_id = "s41586-023-06328-6_protein-protease-resistance"
        rows = [
            (
                "lib1",
                "trypsin",
                6763,
                5663,
                -1.1617873243132126,
                -1.618150718606153,
                -0.6296917374300375,
                0.12328820625661929,
                0,
            ),
            (
                "lib1",
                "chymotrypsin",
                6763,
                4743,
                -1.160547035519476,
                -1.7793063438040733,
                -0.6094363436760983,
                0.0629881784745378,
                0,
            ),
            ("lib1", "cross", 6763, 4536, 0, 0, 0, 0, 0.7661809239863406),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary = root / "resistance_holdout_summary.csv"
            with summary.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(
                    [
                        "library",
                        "protease",
                        "fold0_group_count",
                        "qc_pass_groups",
                        "median_norm_log_survival_auc",
                        "q10_norm_log_survival_auc",
                        "q90_norm_log_survival_auc",
                        "replicate_mae_median",
                        "cross_protease_spearman",
                    ]
                )
                writer.writerows(rows)
            manifest = root / "analysis_manifest.json"
            manifest.write_text(
                json.dumps({"artifacts": [{"path": summary.name}]}),
                encoding="utf-8",
            )
            output = evaluate_problem_artifacts(problem_id, manifest, root, True)
            assert output is not None
            self.assertEqual(output.failures, [])
            self.assertIn("mismatches=0", output.summary)

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
