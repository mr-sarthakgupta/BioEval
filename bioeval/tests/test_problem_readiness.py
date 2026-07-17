from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from bioeval.catalog import load_catalog, resolve_entry_files
from bioeval.guard import enforce, scan_file
from bioeval.problems import list_problem_specs, load_problem_spec, validate_problem_ready


REPO_ROOT = Path(__file__).resolve().parents[2]
PROBLEMS_ROOT = REPO_ROOT / "problems_complete"
INCOMPLETE_ROOT = REPO_ROOT / "problems_imcomplete"

FORGE_ID = "s41467-026-73977-2_forge-cancer-drug-response"
F1_ID = "s41467-026-73844-0_f1-atpase-markov-model"
PLANT_ID = "s41586-022-05383-9_light-competition-plant-diversity"
PROTEIN_ID = "s41586-023-06328-6_protein-protease-resistance"
METHANE_ID = "s41586-023-06344-6_global-river-methane"
CHROMATIN_ID = "nature09906_chromatin-state-dynamics"
IDR_ID = "s41589-026-02251-9_idr-condensate-serine-charge"


class ProblemReadinessTests(unittest.TestCase):
    def test_only_ready_problems_are_active(self) -> None:
        active = {
            spec.problem_id
            for spec in list_problem_specs()
            if spec.benchmark_status == "active"
        }
        self.assertEqual(
            active,
            {FORGE_ID, F1_ID, PROTEIN_ID, IDR_ID, "s41467-026-73635-7_butterfly-longevity-pollen-feeding"},
        )
        for problem_id in active:
            self.assertEqual(validate_problem_ready(load_problem_spec(problem_id), REPO_ROOT), [])
        self.assertEqual(load_problem_spec(PLANT_ID).benchmark_status, "conditional")
        self.assertEqual(load_problem_spec(CHROMATIN_ID).benchmark_status, "conditional")

    def test_idr_grants_only_curated_observations_and_hidden_templates(self) -> None:
        root = PROBLEMS_ROOT / IDR_ID
        spec = load_problem_spec(IDR_ID)
        identifiers = [spec.title, spec.doi, *spec.leak_markers]
        catalog = load_catalog(root)
        grantable = [
            path
            for entry in catalog.entries
            if entry.grantable
            for path in resolve_entry_files(root, entry)
        ]
        self.assertTrue(grantable)
        self.assertTrue(all("curated" in path.parts for path in grantable))
        self.assertTrue(all(scan_file(path, identifiers) is None for path in grantable))
        workbook = (
            root
            / "data"
            / "nature-supplementary"
            / "41589_2026_2251_MOESM10_ESM.xlsx"
        )
        self.assertIsNotNone(scan_file(workbook, identifiers))

    def test_forge_target_aliases_cover_every_training_drug(self) -> None:
        root = PROBLEMS_ROOT / FORGE_ID / "curated"
        with (root / "drug_target_map.csv").open(newline="") as handle:
            mapped = {row["Drug"] for row in csv.DictReader(handle)}
        with (root / "drug_response_train.csv").open(newline="") as handle:
            drugs = {row["drug"] for row in csv.DictReader(handle)}
        self.assertLessEqual(drugs, mapped)

    def test_new_candidates_declare_lineage_and_external_cutoffs(self) -> None:
        for problem_id in (PLANT_ID, PROTEIN_ID, METHANE_ID, CHROMATIN_ID):
            spec = load_problem_spec(problem_id)
            self.assertIsNotNone(spec.target_footprint_date)
            self.assertIsNotNone(spec.external_source_cutoff)
            assert spec.target_footprint_date is not None
            assert spec.external_source_cutoff is not None
            self.assertLess(
                spec.external_source_cutoff.date(),
                spec.target_footprint_date,
            )

    def test_forge_is_architecture_independent_and_has_alignment_inputs(self) -> None:
        spec = load_problem_spec(FORGE_ID)
        prompt = spec.sandbox_prompt.lower()
        rubric = " ".join(spec.judge_rubric).lower()
        self.assertIn("any statistically defensible model", prompt)
        self.assertNotIn("shared-representation model", rubric)
        self.assertIn("recomputed", rubric)

        root = PROBLEMS_ROOT / FORGE_ID
        catalog = load_catalog(root)
        for entry_id in ("drug_target_map", "fixed_cell_line_split"):
            entry = catalog.by_id(entry_id)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertTrue(entry.grantable)
            self.assertTrue(resolve_entry_files(root, entry))

        for entry_id in ("drug_response_training_labels", "drug_response_test_rows"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertTrue(entry.grantable)
            self.assertTrue(resolve_entry_files(root, entry))
        for entry_id in ("full_drug_response_matrix", "heldout_drug_response_labels"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)
        online = catalog.by_id("public_figshare_record")
        assert online is not None and online.online is not None
        self.assertIn("Creammist_common_ic50.csv", online.online["exclude"])

        with (root / "curated" / "drug_response_test_rows.csv").open(newline="") as handle:
            self.assertEqual(
                next(csv.reader(handle)),
                ["drug", "cell_line_id"],
            )

    def test_forge_split_is_deterministic_and_nonempty(self) -> None:
        path = (
            PROBLEMS_ROOT
            / FORGE_ID
            / "curated"
            / "cell_line_split.csv"
        )
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 700)
        self.assertEqual({row["split"] for row in rows}, {"train", "test"})
        for row in rows:
            digest = hashlib.sha256(
                ("bioeval-forge-v1:" + row["cell_line_id"]).encode()
            ).digest()
            expected = "test" if int.from_bytes(digest[:8], "big") % 5 == 0 else "train"
            self.assertEqual(row["split"], expected)

    def test_f1_separates_training_validation_and_blocks_target_outputs(self) -> None:
        spec = load_problem_spec(F1_ID)
        prompt = spec.sandbox_prompt.lower()
        self.assertIn("three-conformation class", prompt)
        self.assertIn("conditional on this model family", prompt)

        root = PROBLEMS_ROOT / F1_ID
        catalog = load_catalog(root)
        for entry_id in (
            "turnover_and_coupling_training_observations",
            "independent_mechanistic_validation_constraints",
        ):
            entry = catalog.by_id(entry_id)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertTrue(entry.grantable)
            files = resolve_entry_files(root, entry)
            self.assertTrue(files)
            identifiers = [spec.title, spec.doi, *spec.leak_markers]
            self.assertTrue(all(scan_file(path, identifiers) is None for path in files))

        for entry_id in (
            "target_paper_source_data_archive",
            "target_paper_supplementary_information",
        ):
            entry = catalog.by_id(entry_id)
            self.assertIsNotNone(entry)
            assert entry is not None
            self.assertFalse(entry.grantable)

    def test_new_curated_tables_clear_the_leak_boundary(self) -> None:
        cases = {
            FORGE_ID: (
                "drug_target_map",
                "fixed_cell_line_split",
                "drug_response_training_labels",
                "drug_response_test_rows",
            ),
            F1_ID: (
                "turnover_and_coupling_training_observations",
                "independent_mechanistic_validation_constraints",
            ),
        }
        for problem_id, entry_ids in cases.items():
            root = PROBLEMS_ROOT / problem_id
            catalog = load_catalog(root)
            spec = load_problem_spec(problem_id)
            with self.subTest(problem_id=problem_id), tempfile.TemporaryDirectory() as tmp:
                stage = Path(tmp)
                expected = 0
                for entry_id in entry_ids:
                    entry = catalog.by_id(entry_id)
                    assert entry is not None
                    for source in resolve_entry_files(root, entry):
                        expected += 1
                        shutil.copy2(source, stage / f"{expected:02d}_{source.name}")
                report = enforce(
                    stage,
                    [spec.problem_id, spec.title, spec.doi, *spec.leak_markers],
                )
                self.assertEqual(len(report.kept), expected)
                self.assertFalse(report.rejected)

    def test_plant_snapshot_is_pinned_and_answer_outputs_are_blocked(self) -> None:
        spec = load_problem_spec(PLANT_ID)
        self.assertIn("pseudoreplication", " ".join(spec.judge_rubric).lower())
        root = PROBLEMS_ROOT / PLANT_ID
        catalog = load_catalog(root)
        online = catalog.by_id("pinned_dryad_snapshot")
        assert online is not None and online.online is not None
        self.assertTrue(online.grantable)
        self.assertEqual(online.online["provider"], "dryad")
        self.assertEqual(online.online["version_id"], 204170)
        for entry_id in ("derived_trait_response_tables", "dataset_readme", "author_analysis_code"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)

        manifest = json.loads((root / "curated" / "source_manifest.json").read_text())
        self.assertEqual(manifest["version_id"], 204170)
        self.assertEqual(len(manifest["files"]), 14)
        self.assertEqual(sum(row["bytes"] for row in manifest["files"]), 1_276_692)
        self.assertTrue(all(len(row["sha256"]) == 64 for row in manifest["files"]))

    def test_protein_scope_uses_raw_counts_and_neutral_condition_map(self) -> None:
        spec = load_problem_spec(PROTEIN_ID)
        self.assertIn("not fastq", spec.sandbox_prompt.lower())
        self.assertIn("absolute delta-g", spec.expected_caveats[-1].lower())
        root = PROBLEMS_ROOT / PROTEIN_ID
        catalog = load_catalog(root)
        counts = catalog.by_id("exact_match_ngs_counts")
        conditions = catalog.by_id("assay_condition_map")
        assert counts is not None and conditions is not None
        count_files = resolve_entry_files(root, counts)
        self.assertEqual(len(count_files), 4)
        self.assertEqual(
            sum(path.stat().st_size for path in count_files),
            1_229_590_882,
        )
        self.assertEqual(len(resolve_entry_files(root, conditions)), 1)
        for entry_id in ("public_raw_count_archive", "fitted_stability_tables", "author_pipelines"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)

        with (root / "curated" / "assay_conditions.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 48)
        self.assertEqual(sum(row["is_no_protease_control"] == "True" for row in rows), 4)

    def test_methane_candidate_pins_observations_and_blocks_global_outputs(self) -> None:
        spec = load_problem_spec(METHANE_ID)
        self.assertIn("do not estimate global annual", spec.sandbox_prompt.lower())
        root = INCOMPLETE_ROOT / METHANE_ID
        catalog = load_catalog(root)
        for entry_id in (
            "river_methane_concentrations",
            "measured_river_methane_fluxes",
            "river_site_covariates",
            "observation_source_keys",
            "fixed_source_folds",
        ):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertTrue(entry.grantable)
            self.assertTrue(resolve_entry_files(root, entry))
        for entry_id in ("target_mixed_model_archive", "target_global_rasters"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)

        with (root / "curated" / "source_folds.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 298)
        for row in rows:
            digest = hashlib.sha256(
                ("bioeval-grimedb-v1:" + row["Source_ID"]).encode()
            ).digest()
            self.assertEqual(int(row["fold"]), int.from_bytes(digest[:8], "big") % 5)

    def test_chromatin_manifests_are_exact_and_target_states_are_blocked(self) -> None:
        spec = load_problem_spec(CHROMATIN_ID)
        self.assertIn("label-invariant", spec.sandbox_prompt.lower())
        root = INCOMPLETE_ROOT / CHROMATIN_ID
        catalog = load_catalog(root)
        for entry_id in ("published_state_segmentations", "published_state_labels_and_models"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)

        with (root / "curated" / "core_bed_manifest.csv").open(newline="") as handle:
            core = list(csv.DictReader(handle))
        with (root / "curated" / "expression_cel_manifest.csv").open(newline="") as handle:
            cel = list(csv.DictReader(handle))
        self.assertEqual(len(core), 178)
        self.assertEqual(sum(int(row["bytes"]) for row in core), 44_368_287_353)
        self.assertEqual(len(cel), 19)
        self.assertEqual(sum(int(row["bytes"]) for row in cel), 49_106_218)
        self.assertNotIn("H3K9me3", {row["mark"] for row in core})


if __name__ == "__main__":
    unittest.main()
