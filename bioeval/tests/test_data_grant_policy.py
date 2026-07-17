from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import pandas as pd

from bioeval.catalog import resolve_entry_files
from bioeval.curation import (
    DENIED_RE,
    GrantPlan,
    StageInstruction,
    specificity_issue,
    stage_and_grant,
)
from bioeval.schemas import CatalogEntry, DataCatalog, DatasetRequest


class DataGrantPolicyTests(unittest.TestCase):
    def test_problem_relative_grants_are_confined_to_curated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "curated").mkdir()
            (root / "evaluator").mkdir()
            (root / "curated" / "safe.csv").write_text("x\n1\n")
            (root / "evaluator" / "labels.csv").write_text("label\nsecret\n")
            safe = CatalogEntry(
                id="safe",
                description="safe curated data",
                source_base="problem",
                source_paths=["curated/safe.csv"],
            )
            hidden = CatalogEntry(
                id="hidden",
                description="hidden evaluator labels",
                source_base="problem",
                source_paths=["evaluator/labels.csv"],
            )
            self.assertEqual(len(resolve_entry_files(root, safe)), 1)
            self.assertEqual(resolve_entry_files(root, hidden), [])

    def test_concrete_request_with_captivity_is_specific(self) -> None:
        request = DatasetRequest(
            question=(
                "Maximum adult lifespan in days for Drosophila melanogaster "
                "reared in captivity."
            ),
            desired_modalities=["survival"],
        )

        self.assertIsNone(specificity_issue(request))

    def test_inventory_request_is_denied(self) -> None:
        request = DatasetRequest(
            question="Do you have any survival datasets for butterflies?",
            desired_modalities=["survival"],
        )

        self.assertIsNotNone(specificity_issue(request))

    def test_named_public_repository_accession_is_allowed_to_planning(self) -> None:
        question = (
            "Peak-by-cell accessibility matrix from the public GEO repository "
            "record GSE96769."
        )
        request = DatasetRequest(
            question=question,
            desired_modalities=["scATAC-seq"],
        )

        self.assertIsNone(DENIED_RE.search(question))
        self.assertIsNone(specificity_issue(request))

    def test_explicit_columns_are_a_hard_grant_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            problem_root = root / "problem"
            data_root = problem_root / "data"
            data_root.mkdir(parents=True)
            pd.DataFrame(
                {
                    "individual_id": [1, 2, 3],
                    "days_survived": [10, 20, 30],
                    "sex": ["F", "M", "F"],
                    "hidden_extra": ["a", "b", "c"],
                }
            ).to_csv(data_root / "survival.csv", index=False)
            catalog = DataCatalog(
                problem_id="test",
                entries=[
                    CatalogEntry(
                        id="survival",
                        description=(
                            "Individual Drosophila melanogaster survival records "
                            "under laboratory diet conditions."
                        ),
                        modalities=["survival", "csv"],
                        source_paths=["survival.csv"],
                    )
                ],
            )
            request = DatasetRequest(
                question=(
                    "Individual survival records for Drosophila melanogaster under "
                    "control laboratory diet conditions."
                ),
                desired_modalities=["survival"],
                desired_columns=["individual_id", "days_survived"],
                max_rows=2,
            )

            grant = stage_and_grant(
                problem_root=problem_root,
                catalog=catalog,
                identifiers=[],
                staging_root=root / "grants",
                sandbox_data_root="/workspace/data",
                request=request,
                request_id="request1",
                plan=GrantPlan(instructions=[StageInstruction(entry_id="survival")]),
            )

            self.assertIn(grant.status, {"granted", "partial"})
            output = pd.read_csv(root / "grants/request1/dataset_001/file_001.csv")
            self.assertEqual(list(output.columns), ["individual_id", "days_survived"])
            self.assertEqual(len(output), 2)

    def test_failed_column_subset_never_falls_back_to_full_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            problem_root = root / "problem"
            data_root = problem_root / "data"
            data_root.mkdir(parents=True)
            pd.DataFrame(
                {"individual_id": [1], "days_survived": [10], "secret": ["value"]}
            ).to_csv(data_root / "survival.csv", index=False)
            catalog = DataCatalog(
                problem_id="test",
                entries=[
                    CatalogEntry(
                        id="survival",
                        description="Drosophila melanogaster laboratory survival records.",
                        modalities=["survival", "csv"],
                        source_paths=["survival.csv"],
                    )
                ],
            )
            request = DatasetRequest(
                question=(
                    "Individual survival records for Drosophila melanogaster under "
                    "control laboratory conditions."
                ),
                desired_modalities=["survival"],
                desired_columns=["column_that_does_not_exist"],
            )

            grant = stage_and_grant(
                problem_root=problem_root,
                catalog=catalog,
                identifiers=[],
                staging_root=root / "grants",
                sandbox_data_root="/workspace/data",
                request=request,
                request_id="request2",
                plan=GrantPlan(instructions=[StageInstruction(entry_id="survival")]),
            )

            self.assertEqual(grant.status, "denied")
            self.assertEqual(grant.denial_category, "asset_unavailable")
            self.assertEqual(grant.files, [])


if __name__ == "__main__":
    unittest.main()
