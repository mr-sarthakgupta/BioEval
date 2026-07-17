"""JSON Schema used by the research-agent's design_experiment tool."""

from __future__ import annotations


def experiment_tool_schema() -> dict:
    string = {"type": "string", "minLength": 1}
    string_array = {"type": "array", "items": string, "minItems": 1}
    named_value = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": string,
            "value": {"type": ["string", "number", "integer", "boolean"]},
            "unit": {"type": ["string", "null"]},
            "tolerance": {"type": ["string", "null"]},
            "method": {"type": ["string", "null"]},
        },
        "required": ["name", "value", "unit", "tolerance", "method"],
    }
    entity = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": string,
            "role": string,
            "kind": {
                "type": "string",
                "enum": [
                    "organism",
                    "cell_model",
                    "cohort",
                    "chemical",
                    "material",
                    "physical_system",
                    "environmental_sample",
                    "computational_model",
                    "other",
                ],
            },
            "name": string,
            "identifiers": {"type": "array", "items": string},
            "properties": {"type": "array", "items": named_value, "minItems": 1},
        },
        "required": ["id", "role", "kind", "name", "identifiers", "properties"],
    }
    group = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": string,
            "role": {
                "type": "string",
                "enum": ["control", "treatment", "reference", "observational", "calibration", "other"],
            },
            "description": string,
            "entity_ids": string_array,
            "sample_size": {"type": "integer", "minimum": 1},
            "biological_replicates": {"type": "integer", "minimum": 1},
            "technical_replicates": {"type": "integer", "minimum": 1},
        },
        "required": [
            "id",
            "role",
            "description",
            "entity_ids",
            "sample_size",
            "biological_replicates",
            "technical_replicates",
        ],
    }
    factor = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": string,
            "levels": {"type": "array", "items": named_value, "minItems": 1},
            "assignment": string,
        },
        "required": ["name", "levels", "assignment"],
    }
    design = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "design_type": {
                "type": "string",
                "enum": [
                    "controlled",
                    "factorial",
                    "dose_response",
                    "time_series",
                    "observational",
                    "cohort",
                    "field",
                    "simulation",
                    "other",
                ],
            },
            "experimental_unit": string,
            "groups": {"type": "array", "items": group, "minItems": 1},
            "factors": {"type": "array", "items": factor, "minItems": 1},
            "controls": {"type": "array", "items": string},
            "allocation": string,
            "randomization": string,
            "blinding": string,
            "power_or_sample_size_rationale": string,
        },
        "required": [
            "design_type",
            "experimental_unit",
            "groups",
            "factors",
            "controls",
            "allocation",
            "randomization",
            "blinding",
            "power_or_sample_size_rationale",
        ],
    }
    intervention = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": string,
            "target_group_ids": string_array,
            "agent_entity_id": {"type": ["string", "null"]},
            "manipulation": string,
            "parameters": {"type": "array", "items": named_value, "minItems": 1},
            "route_or_method": string,
            "timing": string,
            "duration": named_value,
            "frequency": string,
        },
        "required": [
            "id",
            "target_group_ids",
            "agent_entity_id",
            "manipulation",
            "parameters",
            "route_or_method",
            "timing",
            "duration",
            "frequency",
        ],
    }
    procedure = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "order": {"type": "integer", "minimum": 1},
            "action": string,
            "entity_ids": string_array,
            "equipment": string_array,
            "parameters": {"type": "array", "items": named_value, "minItems": 1},
            "timing": string,
            "quality_control": string,
        },
        "required": [
            "order",
            "action",
            "entity_ids",
            "equipment",
            "parameters",
            "timing",
            "quality_control",
        ],
    }
    measurement = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": string,
            "target_entity_ids": string_array,
            "property": string,
            "method": string,
            "instrument_or_assay": string,
            "unit": string,
            "timepoints": string_array,
            "resolution": string,
            "aggregation_level": string,
        },
        "required": [
            "id",
            "target_entity_ids",
            "property",
            "method",
            "instrument_or_assay",
            "unit",
            "timepoints",
            "resolution",
            "aggregation_level",
        ],
    }
    data_field = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "name": string,
            "description": string,
            "data_type": {
                "type": "string",
                "enum": ["string", "integer", "number", "boolean", "datetime", "category", "array"],
            },
            "unit": {"type": ["string", "null"]},
        },
        "required": ["name", "description", "data_type", "unit"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "title": string,
            "domain": string,
            "objective": string,
            "hypothesis": {"type": ["string", "null"]},
            "hypothesis_not_applicable_reason": {"type": ["string", "null"]},
            "entities": {"type": "array", "items": entity, "minItems": 1},
            "design": design,
            "interventions": {"type": "array", "items": intervention},
            "environment": {"type": "array", "items": named_value, "minItems": 1},
            "procedures": {"type": "array", "items": procedure, "minItems": 1},
            "measurements": {"type": "array", "items": measurement, "minItems": 1},
            "data_product": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "observation_unit": string,
                    "fields": {"type": "array", "items": data_field, "minItems": 1},
                    "formats": string_array,
                    "max_rows": {"type": ["integer", "null"], "minimum": 1},
                    "max_bytes": {"type": "integer", "minimum": 1000000},
                },
                "required": ["observation_unit", "fields", "formats", "max_rows", "max_bytes"],
            },
            "feasibility_constraints": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "maximum_duration": string,
                    "available_resources": string_array,
                    "safety_and_ethics": string_array,
                    "assumptions": string_array,
                },
                "required": [
                    "maximum_duration",
                    "available_resources",
                    "safety_and_ethics",
                    "assumptions",
                ],
            },
        },
        "required": [
            "schema_version",
            "title",
            "domain",
            "objective",
            "hypothesis",
            "hypothesis_not_applicable_reason",
            "entities",
            "design",
            "interventions",
            "environment",
            "procedures",
            "measurements",
            "data_product",
            "feasibility_constraints",
        ],
    }
