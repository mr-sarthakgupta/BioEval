"""Validate experiment designs before any catalog or network access."""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from typing import Any

from bioeval.bedrock_client import (
    create_bedrock_client,
    extract_text_from_response,
    is_bedrock_api_base,
    prompt_cache_point,
)
from bioeval.schemas import (
    ExperimentRequest,
    ExperimentValidation,
    ValidationCheck,
)


FEASIBILITY_SYSTEM_PROMPT = """You are an independent experiment feasibility reviewer.
You receive one structured hypothetical experiment and must decide whether it could
realistically generate the requested measurements. You do not know what datasets are
available and must not infer availability.

Return feasible only when the design is reproducible, internally consistent, measurable,
adequately controlled/replicated for its stated purpose, physically and scientifically
plausible, and compatible with the stated resources, duration, safety, and ethics.
Return needs_revision for missing, ambiguous, or repairable details. Return unrealistic
when the proposed mechanism, method, timing, scale, precision, or resources cannot
realistically produce the requested output. Return restricted for unsafe, unethical, or
disallowed work. Give concise field-path checks. Do not rewrite the protocol and do not
claim the experiment was performed."""
LOGGER = logging.getLogger(__name__)


def _check(
    category: str,
    path: str,
    message: str,
    severity: str = "error",
) -> ValidationCheck:
    return ValidationCheck(
        category=category,
        severity=severity,
        path=path,
        message=message,
    )


def deterministic_validation(request: ExperimentRequest) -> ExperimentValidation | None:
    """Return a revision result for semantic omissions not expressible in JSON Schema."""
    checks: list[ValidationCheck] = []
    entity_ids = {entity.id for entity in request.entities}
    measurement_ids = [measurement.id for measurement in request.measurements]
    if len(measurement_ids) != len(set(measurement_ids)):
        checks.append(
            _check("consistency", "measurements", "Measurement IDs must be unique.")
        )
    for index, entity in enumerate(request.entities):
        if entity.kind != "other" and not entity.identifiers:
            checks.append(
                _check(
                    "completeness",
                    f"entities[{index}].identifiers",
                    "Provide a stable taxonomy, strain, cell-line, CAS, grade, or model identifier.",
                )
            )
        for prop_index, prop in enumerate(entity.properties):
            if isinstance(prop.value, (int, float)) and not prop.unit:
                checks.append(
                    _check(
                        "completeness",
                        f"entities[{index}].properties[{prop_index}].unit",
                        "Numeric properties require an explicit unit or 'dimensionless'.",
                    )
                )
    if request.design.design_type in {"controlled", "factorial", "dose_response"}:
        if not request.interventions:
            checks.append(
                _check(
                    "completeness",
                    "interventions",
                    "This design type requires at least one explicit intervention.",
                )
            )
        control_ids = {
            group.id for group in request.design.groups if group.role == "control"
        }
        if not control_ids:
            checks.append(
                _check(
                    "controls",
                    "design.groups",
                    "This design type requires a group with role 'control'.",
                )
            )
    for index, intervention in enumerate(request.interventions):
        if intervention.agent_entity_id and intervention.agent_entity_id not in entity_ids:
            checks.append(
                _check(
                    "consistency",
                    f"interventions[{index}].agent_entity_id",
                    "The intervention agent must reference a declared entity.",
                )
            )
        for param_index, param in enumerate(intervention.parameters):
            if isinstance(param.value, (int, float)) and not param.unit:
                checks.append(
                    _check(
                        "completeness",
                        f"interventions[{index}].parameters[{param_index}].unit",
                        "Numeric intervention parameters require an explicit unit.",
                    )
                )
    declared_fields = {field.name.lower() for field in request.data_product.fields}
    for index, measurement in enumerate(request.measurements):
        if measurement.property.lower() not in declared_fields and not any(
            measurement.property.lower() in field.description.lower()
            for field in request.data_product.fields
        ):
            checks.append(
                _check(
                    "consistency",
                    f"measurements[{index}].property",
                    "The measured property must map to a declared data-product field.",
                )
            )
    if checks:
        return ExperimentValidation(
            status="needs_revision",
            summary="The experiment specification has repairable omissions or inconsistencies.",
            checks=checks,
        )
    return None


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start : end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _strict_output_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Make every object property required for strict-output providers."""
    result = deepcopy(schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                node["additionalProperties"] = False
                node["required"] = list(properties)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(result)
    return result


def _with_bedrock(
    request: ExperimentRequest,
    *,
    model: str,
    api_base: str,
) -> ExperimentValidation | None:
    client = create_bedrock_client(api_base)
    schema = _strict_output_schema(ExperimentValidation.model_json_schema())
    cache_point = prompt_cache_point()
    response = client.converse(
        modelId=model.removeprefix("bedrock/"),
        system=[{"text": FEASIBILITY_SYSTEM_PROMPT}, *([cache_point] if cache_point else [])],
        messages=[
            {
                "role": "user",
                "content": [{"text": request.model_dump_json(exclude={"problem_id"})}],
            }
        ],
        toolConfig={
            "tools": [
                {
                    "toolSpec": {
                        "name": "record_feasibility",
                        "description": "Record the independent feasibility decision.",
                        "inputSchema": {"json": schema},
                    }
                }
            ],
            "toolChoice": {"tool": {"name": "record_feasibility"}},
        },
        inferenceConfig={
            "maxTokens": int(os.getenv("EXPERIMENT_AGENT_VALIDATION_MAX_TOKENS", "4096")),
            "temperature": 0,
        },
    )
    from bioeval.bedrock_cost import record_bedrock_usage

    record_bedrock_usage(
        response.get("usage", {}) or {},
        component="experiment-agent-validation",
        model=model,
    )
    for item in response.get("output", {}).get("message", {}).get("content", []):
        tool_use = item.get("toolUse") if isinstance(item, dict) else None
        if tool_use and tool_use.get("name") == "record_feasibility":
            return ExperimentValidation.model_validate(tool_use.get("input"))
    obj = _extract_json(extract_text_from_response(response))
    return ExperimentValidation.model_validate(obj) if obj else None


def _with_openai(
    request: ExperimentRequest,
    *,
    model: str,
) -> ExperimentValidation | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    from openai import OpenAI

    response = OpenAI().responses.create(
        model=model,
        input=[
            {"role": "system", "content": FEASIBILITY_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": request.model_dump_json(exclude={"problem_id"}),
            },
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "experiment_validation",
                "schema": _strict_output_schema(ExperimentValidation.model_json_schema()),
                "strict": True,
            }
        },
    )
    obj = _extract_json(response.output_text)
    return ExperimentValidation.model_validate(obj) if obj else None


def validate_experiment(
    request: ExperimentRequest,
    *,
    model: str,
    api_base: str,
) -> ExperimentValidation:
    deterministic = deterministic_validation(request)
    if deterministic is not None:
        return deterministic
    try:
        result = (
            _with_bedrock(request, model=model, api_base=api_base)
            if is_bedrock_api_base(api_base)
            else _with_openai(request, model=model)
        )
    except Exception as exc:  # noqa: BLE001 - validation must fail closed
        result = None
        LOGGER.exception("Independent feasibility validation failed")
    else:
        if result is None:
            LOGGER.error("Feasibility model returned no valid structured decision")
    if result is not None:
        return result
    return ExperimentValidation(
        status="needs_revision",
        summary="Feasibility could not be established, so execution was not attempted.",
        checks=[
            _check(
                "plausibility",
                "$",
                "Independent feasibility validation is temporarily unavailable.",
            )
        ],
    )
