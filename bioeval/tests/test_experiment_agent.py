from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bioeval.curation import GrantPlan, StageInstruction
from bioeval.experiment_agent import ExperimentAgentSettings, create_app
from bioeval.experiment_validation import deterministic_validation
from bioeval.schemas import (
    DataCatalog,
    DatasetGrant,
    ExperimentRequest,
    ExperimentValidation,
)


def experiment_payload() -> dict:
    value = lambda name, item, unit=None: {  # noqa: E731 - compact test fixture
        "name": name,
        "value": item,
        "unit": unit,
        "tolerance": None,
        "method": None,
    }
    return {
        "schema_version": "1.0",
        "title": "Diet restriction survival experiment",
        "domain": "organismal biology",
        "objective": "Measure adult survival under control and protein-restricted diets.",
        "hypothesis": "Protein restriction changes adult survival.",
        "hypothesis_not_applicable_reason": None,
        "entities": [
            {
                "id": "flies",
                "role": "experimental subject",
                "kind": "organism",
                "name": "Drosophila melanogaster",
                "identifiers": ["NCBI:7227", "Canton-S"],
                "properties": [value("age", 1, "day")],
            },
            {
                "id": "diet",
                "role": "intervention agent",
                "kind": "material",
                "name": "defined laboratory diet",
                "identifiers": ["formulation-v1"],
                "properties": [value("protein concentration", 10, "g/L")],
            },
        ],
        "design": {
            "design_type": "controlled",
            "experimental_unit": "individual adult fly",
            "groups": [
                {
                    "id": "control",
                    "role": "control",
                    "description": "Standard defined diet",
                    "entity_ids": ["flies", "diet"],
                    "sample_size": 50,
                    "biological_replicates": 3,
                    "technical_replicates": 1,
                },
                {
                    "id": "restricted",
                    "role": "treatment",
                    "description": "Protein-restricted defined diet",
                    "entity_ids": ["flies", "diet"],
                    "sample_size": 50,
                    "biological_replicates": 3,
                    "technical_replicates": 1,
                },
            ],
            "factors": [
                {
                    "name": "diet",
                    "levels": [value("control", 10, "g/L"), value("restricted", 5, "g/L")],
                    "assignment": "control and restricted groups respectively",
                }
            ],
            "controls": ["control"],
            "allocation": "Equal allocation to each group.",
            "randomization": "Random assignment after adult collection.",
            "blinding": "Outcome scoring blinded to encoded diet labels.",
            "power_or_sample_size_rationale": "Three cohorts of fifty provide survival-curve precision.",
        },
        "interventions": [
            {
                "id": "diet_assignment",
                "target_group_ids": ["control", "restricted"],
                "agent_entity_id": "diet",
                "manipulation": "Feed the assigned defined diet.",
                "parameters": [value("protein concentration", 5, "g/L")],
                "route_or_method": "ad libitum feeding",
                "timing": "from day one of adulthood",
                "duration": value("duration", 60, "day"),
                "frequency": "continuous with food replacement every two days",
            }
        ],
        "environment": [
            value("temperature", 25, "degC"),
            value("light cycle", "12:12", "hour"),
        ],
        "procedures": [
            {
                "order": 1,
                "action": "Allocate adults to encoded diet groups.",
                "entity_ids": ["flies", "diet"],
                "equipment": ["controlled incubator"],
                "parameters": [value("flies per vial", 10, "count")],
                "timing": "day one",
                "quality_control": "Exclude injured flies before allocation.",
            }
        ],
        "measurements": [
            {
                "id": "survival",
                "target_entity_ids": ["flies"],
                "property": "days_survived",
                "method": "daily census",
                "instrument_or_assay": "survival assay",
                "unit": "day",
                "timepoints": ["daily"],
                "resolution": "one day",
                "aggregation_level": "individual",
            }
        ],
        "data_product": {
            "observation_unit": "individual fly",
            "fields": [
                {
                    "name": "days_survived",
                    "description": "Observed adult survival duration",
                    "data_type": "number",
                    "unit": "day",
                }
            ],
            "formats": ["csv"],
            "max_rows": 300,
            "max_bytes": 10_000_000,
        },
        "feasibility_constraints": {
            "maximum_duration": "90 days",
            "available_resources": ["controlled incubator", "defined diets", "trained scorer"],
            "safety_and_ethics": ["standard containment for Drosophila"],
            "assumptions": ["Canton-S adults are available"],
        },
    }


class ExperimentContractTests(unittest.TestCase):
    def test_cross_references_and_closed_schema_are_enforced(self) -> None:
        payload = experiment_payload()
        payload["design"]["groups"][0]["entity_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            ExperimentRequest.model_validate(payload)

    def test_numeric_property_requires_unit(self) -> None:
        payload = experiment_payload()
        payload["entities"][0]["properties"][0]["unit"] = None
        request = ExperimentRequest.model_validate(payload)
        validation = deterministic_validation(request)
        self.assertIsNotNone(validation)
        self.assertEqual(validation.status, "needs_revision")
        self.assertIn("entities[0].properties[0].unit", validation.checks[0].path)

    def test_non_feasible_validation_short_circuits_catalog_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "problems/test").mkdir(parents=True)
            app = create_app(
                ExperimentAgentSettings(
                    problems_root=root / "problems",
                    staging_root=root / "staging",
                    default_problem_id="test",
                    enforce_problem_status=False,
                )
            )
            endpoint = next(
                route.endpoint
                for route in app.routes
                if getattr(route, "path", None) == "/experiments"
            )
            validation = ExperimentValidation(
                status="unrealistic",
                summary="The requested precision is physically unattainable.",
            )
            with (
                patch("bioeval.data_agent._identifiers_for", return_value=[]),
                patch("bioeval.data_agent.validate_experiment", return_value=validation),
                patch(
                    "bioeval.data_agent.load_catalog",
                    side_effect=AssertionError("catalog must not be loaded"),
                ),
            ):
                result = endpoint(ExperimentRequest.model_validate(experiment_payload()))
            self.assertEqual(result.execution_status, "not_attempted")
            self.assertEqual(result.validation.status, "unrealistic")

    def test_feasible_experiment_can_receive_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "problems/test").mkdir(parents=True)
            app = create_app(
                ExperimentAgentSettings(
                    problems_root=root / "problems",
                    staging_root=root / "staging",
                    default_problem_id="test",
                    enforce_problem_status=False,
                )
            )
            endpoint = next(
                route.endpoint
                for route in app.routes
                if getattr(route, "path", None) == "/experiments"
            )
            validation = ExperimentValidation(status="feasible", summary="Feasible.")
            grant = DatasetGrant(
                request_id="ignored",
                status="granted",
                message="Placed compatible data in the sandbox.",
            )
            with (
                patch("bioeval.data_agent._identifiers_for", return_value=[]),
                patch("bioeval.data_agent.validate_experiment", return_value=validation),
                patch(
                    "bioeval.data_agent.load_catalog",
                    return_value=DataCatalog(problem_id="test", entries=[]),
                ),
                patch(
                    "bioeval.data_agent.make_plan",
                    return_value=GrantPlan(
                        instructions=[StageInstruction(entry_id="unused")]
                    ),
                ),
                patch("bioeval.data_agent.stage_and_grant", return_value=grant),
            ):
                result = endpoint(ExperimentRequest.model_validate(experiment_payload()))
            self.assertEqual(result.validation.status, "feasible")
            self.assertEqual(result.execution_status, "completed")

    def test_online_discovery_runs_only_after_local_denial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "problems/test").mkdir(parents=True)
            app = create_app(
                ExperimentAgentSettings(
                    problems_root=root / "problems",
                    staging_root=root / "staging",
                    default_problem_id="test",
                    enforce_problem_status=False,
                )
            )
            endpoint = next(
                route.endpoint
                for route in app.routes
                if getattr(route, "path", None) == "/experiments"
            )
            denied = DatasetGrant(
                request_id="ignored",
                status="denied",
                message="No compatible local data.",
                denial_category="no_exact_match",
            )
            granted = DatasetGrant(
                request_id="ignored",
                status="granted",
                message="Placed compatible online data in the sandbox.",
            )
            candidate = {
                "id": "online_zenodo_12345",
                "description": "Drosophila survival under defined diet restriction",
                "modalities": ["online", "dataset"],
                "approx_bytes": 1000,
                "online": {"provider": "zenodo", "record_id": "12345"},
            }
            validation = ExperimentValidation(status="feasible", summary="Feasible.")
            payload = experiment_payload()
            payload["objective"] += " Use public measurements from Zenodo record 12345."
            with (
                patch("bioeval.data_agent._identifiers_for", return_value=[]),
                patch("bioeval.data_agent.validate_experiment", return_value=validation),
                patch(
                    "bioeval.data_agent.load_catalog",
                    return_value=DataCatalog(problem_id="test", entries=[]),
                ),
                patch(
                    "bioeval.data_agent.make_plan",
                    side_effect=[
                        GrantPlan(deny=True, deny_reason="no local match"),
                        GrantPlan(
                            instructions=[
                                StageInstruction(
                                    entry_id="online_zenodo_12345",
                                    use_online=True,
                                )
                            ]
                        ),
                    ],
                ),
                patch(
                    "bioeval.data_agent.stage_and_grant",
                    side_effect=[denied, granted],
                ),
                patch(
                    "bioeval.data_agent.providers.discover_dataset_specs",
                    return_value=[candidate],
                ) as discover,
            ):
                result = endpoint(ExperimentRequest.model_validate(payload))
            discover.assert_called_once()
            self.assertEqual(result.execution_status, "completed")
            rendered = result.model_dump_json().lower()
            self.assertNotIn("zenodo", rendered)
            self.assertNotIn("matched", rendered)
            self.assertNotIn("local", rendered)


if __name__ == "__main__":
    unittest.main()
