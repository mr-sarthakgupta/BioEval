from __future__ import annotations

import csv
import gzip
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
HUMAN_MASS_ID = "s41586-020-3010-5_human-made-mass"
BEHAVIOR_ID = "s41586-022-05611-2_spontaneous-behavior"
GASTRULATION_ID = "s41586-019-0933-9_mouse-gastrulation"
GUT_MAG_ID = "s41586-019-1058-x_gut-mag-diversity"
RNA_HYDRATION_ID = "s41586-025-08855-w_rna-hydration"


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
        for problem_id in (
            PLANT_ID,
            PROTEIN_ID,
            METHANE_ID,
            CHROMATIN_ID,
            HUMAN_MASS_ID,
            BEHAVIOR_ID,
            GASTRULATION_ID,
            GUT_MAG_ID,
            RNA_HYDRATION_ID,
        ):
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

    def test_human_mass_stays_acquisition_only_pending_provenance(self) -> None:
        spec = load_problem_spec(HUMAN_MASS_ID)
        self.assertEqual(spec.benchmark_status, "acquisition_only")
        self.assertEqual(spec.expected_conclusions, [])
        self.assertEqual(spec.required_artifacts, [])

        root = INCOMPLETE_ROOT / HUMAN_MASS_ID
        catalog = load_catalog(root)
        self.assertFalse(any(entry.grantable for entry in catalog.entries))

        for entry_id in (
            "post_2015_material_projections",
            "annual_biomass_trajectories",
            "target_sensitivity_and_crossing_outputs",
            "target_repository_code_and_figures",
        ):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)

        audit_root = root / "evaluator" / "host-audit"
        with (audit_root / "annual_material_stocks_1900_2015.csv").open(
            newline=""
        ) as handle:
            material = list(csv.DictReader(handle))
        self.assertEqual(len(material), 116)
        self.assertEqual(
            [int(material[0]["year"]), int(material[-1]["year"])],
            [1900, 2015],
        )
        self.assertNotIn("total", material[0])
        self.assertNotIn("crossing_year", material[0])

        manifest = json.loads((audit_root / "source_manifest.json").read_text())
        self.assertEqual(
            manifest["source_commit"],
            "5a0170a51d164c1cc98b232452e86feb1e4ee334",
        )
        self.assertEqual(len(manifest["sources"]), 2)
        self.assertTrue(all(len(row["sha256"]) == 64 for row in manifest["sources"]))

    def test_spontaneous_behavior_stays_acquisition_only(self) -> None:
        spec = load_problem_spec(BEHAVIOR_ID)
        self.assertEqual(spec.benchmark_status, "acquisition_only")
        self.assertEqual(spec.expected_conclusions, [])
        self.assertEqual(spec.required_artifacts, [])

        root = INCOMPLETE_ROOT / BEHAVIOR_ID
        catalog = load_catalog(root)
        self.assertFalse(any(entry.grantable for entry in catalog.entries))
        archive = catalog.by_id("public_mixed_data_archive")
        assert archive is not None and archive.online is not None
        self.assertEqual(archive.approx_bytes, 60_751_713_398)
        self.assertEqual(archive.online["record_id"], 7274803)

        manifest = json.loads(
            (root / "evaluator" / "host-audit" / "source_manifest.json").read_text()
        )
        self.assertEqual(manifest["record_id"], 7274803)
        self.assertFalse(manifest["downloaded"])
        self.assertFalse(manifest["grantable"])
        self.assertEqual(manifest["files"][0]["bytes"], 60_751_713_398)
        self.assertEqual(
            manifest["files"][0]["checksum"],
            "md5:8b858e447902642555200faf89e00179",
        )

    def test_mouse_gastrulation_pilot_is_conditional_and_label_free(self) -> None:
        spec = load_problem_spec(GASTRULATION_ID)
        self.assertEqual(spec.benchmark_status, "conditional")
        self.assertTrue(spec.expected_conclusions)
        self.assertEqual(
            {item.path for item in spec.required_artifacts},
            {"trajectory_holdout.csv"},
        )

        root = INCOMPLETE_ROOT / GASTRULATION_ID
        catalog = load_catalog(root)
        identifiers = [spec.problem_id, spec.title, spec.doi, *spec.leak_markers]
        for entry_id in (
            "sanitized_count_matrix",
            "neutral_cell_metadata",
            "neutral_gene_metadata",
        ):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertTrue(entry.grantable)
            paths = resolve_entry_files(root, entry)
            self.assertTrue(paths)
            self.assertTrue(all(scan_file(path, identifiers) is None for path in paths))
        for entry_id in (
            "target_atlas_objects_and_annotations",
            "target_trajectory_outputs",
            "full_primary_alignment_archive",
        ):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)

        manifest = json.loads((root / "curated" / "source_manifest.json").read_text())
        self.assertEqual(manifest["primary"]["arrayexpress"], "E-MTAB-6967")
        self.assertEqual(manifest["primary"]["runs"], 2560)
        self.assertEqual(
            manifest["primary"]["alignment_and_index_bytes"],
            1_161_489_907_645,
        )
        profiles = (root / "curated" / "acquisition_profiles.yaml").read_text()
        self.assertIn("sanitized-counts-pilot", profiles)
        self.assertIn("grant_archive: false", profiles)
        sanitized = json.loads((root / "curated" / "sanitized_manifest.json").read_text())
        self.assertEqual(sanitized["selection"]["cells"], 2048)
        self.assertEqual(sanitized["selection"]["genes"], 2108)
        self.assertEqual(sanitized["matrix_nonzero"], 1_152_742)
        with gzip.open(
            root / "curated" / "sanitized-counts" / "counts.mtx.gz",
            "rt",
        ) as handle:
            self.assertTrue(next(handle).startswith("%%MatrixMarket"))
            self.assertEqual(next(handle).strip(), "2108 2048 1152742")
        self.assertEqual(sanitized["selection"]["holdout_cells"], 541)
        with (root / "curated" / "sanitized-counts" / "cells.tsv").open(
            newline=""
        ) as handle:
            cells = list(csv.DictReader(handle, delimiter="\t"))
        holdout_cells = [row for row in cells if row["evaluation_split"] == "holdout"]
        self.assertEqual(len(holdout_cells), 541)
        self.assertTrue(all(not row["stage"] for row in holdout_cells))
        self.assertTrue(all(not row["theiler_stage"] for row in holdout_cells))
        self.assertTrue(all(not row["sequencing_batch"] for row in holdout_cells))
        self.assertTrue(
            all(not row["sample_id"].removeprefix("sample_").isdigit() for row in cells)
        )
        with (root / "evaluator" / "trajectory_holdout_labels.csv").open(
            newline=""
        ) as handle:
            labels = list(csv.DictReader(handle))
        self.assertEqual(
            {row["cell_id"] for row in holdout_cells},
            {row["cell_id"] for row in labels},
        )
        self.assertGreater(
            len({row["baseline_predicted_time"] for row in labels}),
            1,
        )

    def test_gut_mag_answer_bearing_pilot_is_blocked(self) -> None:
        spec = load_problem_spec(GUT_MAG_ID)
        self.assertEqual(spec.benchmark_status, "acquisition_only")
        self.assertEqual(spec.expected_conclusions, [])
        self.assertEqual(spec.required_artifacts, [])

        root = INCOMPLETE_ROOT / GUT_MAG_ID
        catalog = load_catalog(root)
        for entry_id in ("anonymized_pilot_fastas", "neutral_pilot_metadata"):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)
        for entry_id in (
            "preclustering_hgm_genomes",
            "target_clusters_trees_and_taxonomy",
            "target_functional_and_association_outputs",
        ):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)
        preclustering = catalog.by_id("preclustering_hgm_genomes")
        assert preclustering is not None
        self.assertEqual(preclustering.approx_bytes, 40_451_655_328)
        self.assertFalse(any(entry.grantable for entry in catalog.entries))

        audit_root = root / "evaluator" / "host-audit"
        self.assertFalse((root / "curated" / "pilot_selection.csv").exists())
        with (audit_root / "ena_sequence_manifest.csv").open(newline="") as handle:
            inventory = list(csv.DictReader(handle))
        with (audit_root / "pilot_selection.csv").open(newline="") as handle:
            pilot = list(csv.DictReader(handle))
        self.assertEqual(len(inventory), 2058)
        self.assertEqual(sum(int(row["base_count"]) for row in inventory), 4_462_286_565)
        self.assertEqual(len(pilot), 256)
        expected = sorted(
            inventory,
            key=lambda row: hashlib.sha256(
                ("bioeval-gut-mag-v1:" + row["accession"]).encode()
            ).hexdigest(),
        )[:256]
        self.assertEqual(
            [row["accession"] for row in pilot],
            [row["accession"] for row in expected],
        )
        self.assertEqual(
            [row["opaque_genome_id"] for row in pilot],
            [f"genome_{index:04d}" for index in range(1, 257)],
        )
    def test_rna_hydration_grants_only_blind_half_maps_and_polymer(self) -> None:
        spec = load_problem_spec(RNA_HYDRATION_ID)
        self.assertEqual(spec.benchmark_status, "conditional")
        root = INCOMPLETE_ROOT / RNA_HYDRATION_ID
        catalog = load_catalog(root)
        identifiers = [spec.problem_id, spec.title, spec.doi, *spec.leak_markers]

        maps = catalog.by_id("blind_half_maps")
        scaffold = catalog.by_id("polymer_only_reference")
        manifest = catalog.by_id("blind_map_manifest")
        assert maps is not None and scaffold is not None and manifest is not None
        self.assertTrue(maps.grantable)
        self.assertTrue(scaffold.grantable)
        self.assertTrue(manifest.grantable)
        map_paths = resolve_entry_files(root, maps)
        self.assertIn(len(map_paths), {0, 4})
        if map_paths:
            self.assertEqual(sum(path.stat().st_size for path in map_paths), 249_314_120)
        for path in map_paths:
            self.assertNotIn("42498", path.name)
            self.assertNotIn("42499", path.name)
            self.assertIsNone(scan_file(path, identifiers))
            with gzip.open(path, "rb") as handle:
                header = handle.read(1024)
            self.assertNotIn(b"EMD-42498", header)
            self.assertNotIn(b"EMD-42499", header)

        scaffold_path = resolve_entry_files(root, scaffold)[0]
        self.assertIsNone(scan_file(scaffold_path, identifiers))
        for path in resolve_entry_files(root, manifest):
            self.assertIsNone(scan_file(path, identifiers))
        lines = scaffold_path.read_text().splitlines()
        self.assertTrue(any(line.startswith("ATOM  ") for line in lines))
        self.assertFalse(any(line.startswith("HETATM") for line in lines))
        self.assertFalse(any("7EZ0" in line for line in lines))
        self.assertFalse((root / "evaluator" / "hydration_sites.csv").exists())
        with (root / "curated" / "map_manifest.csv").open(newline="") as handle:
            manifest_rows = list(csv.DictReader(handle))
        self.assertEqual(len(manifest_rows), 4)
        self.assertTrue(
            {
                "mode",
                "mapc",
                "mapr",
                "maps",
                "origin_x",
                "voxel_x",
            }.issubset(manifest_rows[0])
        )

        for entry_id in (
            "labeled_source_half_maps",
            "solvent_bearing_atomic_models",
            "target_full_maps_validation_and_simulations",
            "target_repository_and_publication",
        ):
            entry = catalog.by_id(entry_id)
            assert entry is not None
            self.assertFalse(entry.grantable)


if __name__ == "__main__":
    unittest.main()
