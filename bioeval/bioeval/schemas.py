from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NamedValue(StrictModel):
    name: str = Field(..., min_length=1, description="Property or parameter name.")
    value: str | float | int | bool = Field(..., description="Exact value; do not include the unit.")
    unit: str | None = Field(
        default=None,
        description="Explicit unit, or null only for categorical/dimensionless values.",
    )
    tolerance: str | None = Field(default=None, description="Allowed range or uncertainty.")
    method: str | None = Field(default=None, description="How this value is established.")


class ExperimentEntity(StrictModel):
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    role: str = Field(..., min_length=2, description="Role in the experiment.")
    kind: Literal[
        "organism",
        "cell_model",
        "cohort",
        "chemical",
        "material",
        "physical_system",
        "environmental_sample",
        "computational_model",
        "other",
    ]
    name: str = Field(..., min_length=2, description="Exact scientific or technical name.")
    identifiers: list[str] = Field(
        default_factory=list,
        description="Taxonomy, strain, cell-line, CAS, model, grade, or other stable identifiers.",
    )
    properties: list[NamedValue] = Field(
        ...,
        min_length=1,
        description="Properties needed to distinguish and reproduce this entity.",
    )


class ExperimentGroup(StrictModel):
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    role: Literal["control", "treatment", "reference", "observational", "calibration", "other"]
    description: str = Field(..., min_length=5)
    entity_ids: list[str] = Field(..., min_length=1)
    sample_size: int = Field(..., ge=1)
    biological_replicates: int = Field(..., ge=1)
    technical_replicates: int = Field(..., ge=1)


class ExperimentFactor(StrictModel):
    name: str = Field(..., min_length=1)
    levels: list[NamedValue] = Field(..., min_length=1)
    assignment: str = Field(..., min_length=2, description="How levels map to groups or units.")


class ExperimentDesign(StrictModel):
    design_type: Literal[
        "controlled",
        "factorial",
        "dose_response",
        "time_series",
        "observational",
        "cohort",
        "field",
        "simulation",
        "other",
    ]
    experimental_unit: str = Field(..., min_length=2)
    groups: list[ExperimentGroup] = Field(..., min_length=1)
    factors: list[ExperimentFactor] = Field(..., min_length=1)
    controls: list[str] = Field(
        ...,
        description="Control group IDs, or an explicit explanation of why controls do not apply.",
    )
    allocation: str = Field(..., min_length=3)
    randomization: str = Field(..., min_length=3)
    blinding: str = Field(..., min_length=3)
    power_or_sample_size_rationale: str = Field(..., min_length=10)


class Intervention(StrictModel):
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    target_group_ids: list[str] = Field(..., min_length=1)
    agent_entity_id: str | None = None
    manipulation: str = Field(..., min_length=3)
    parameters: list[NamedValue] = Field(..., min_length=1)
    route_or_method: str = Field(..., min_length=2)
    timing: str = Field(..., min_length=2)
    duration: NamedValue
    frequency: str = Field(..., min_length=2)


class ProcedureStep(StrictModel):
    order: int = Field(..., ge=1)
    action: str = Field(..., min_length=5)
    entity_ids: list[str] = Field(..., min_length=1)
    equipment: list[str] = Field(..., min_length=1)
    parameters: list[NamedValue] = Field(..., min_length=1)
    timing: str = Field(..., min_length=2)
    quality_control: str = Field(..., min_length=5)


class Measurement(StrictModel):
    id: str = Field(..., pattern=r"^[a-z][a-z0-9_]*$")
    target_entity_ids: list[str] = Field(..., min_length=1)
    property: str = Field(..., min_length=2)
    method: str = Field(..., min_length=2)
    instrument_or_assay: str = Field(..., min_length=2)
    unit: str = Field(..., min_length=1, description="Use 'dimensionless' when appropriate.")
    timepoints: list[str] = Field(..., min_length=1)
    resolution: str = Field(..., min_length=2)
    aggregation_level: str = Field(..., min_length=2)


class DataField(StrictModel):
    name: str = Field(..., min_length=1)
    description: str = Field(..., min_length=3)
    data_type: Literal["string", "integer", "number", "boolean", "datetime", "category", "array"]
    unit: str | None = None


class DataProduct(StrictModel):
    observation_unit: str = Field(..., min_length=2)
    fields: list[DataField] = Field(..., min_length=1)
    formats: list[str] = Field(..., min_length=1)
    max_rows: int | None = Field(default=None, ge=1)
    max_bytes: int = Field(default=1_000_000_000, ge=1_000_000)


class FeasibilityConstraints(StrictModel):
    maximum_duration: str = Field(..., min_length=2)
    available_resources: list[str] = Field(..., min_length=1)
    safety_and_ethics: list[str] = Field(..., min_length=1)
    assumptions: list[str] = Field(..., min_length=1)


class ExperimentRequest(StrictModel):
    """A reproducible hypothetical experiment submitted by the research agent."""

    schema_version: Literal["1.0"] = "1.0"
    title: str = Field(..., min_length=5)
    domain: str = Field(..., min_length=2)
    objective: str = Field(..., min_length=10)
    hypothesis: str | None
    hypothesis_not_applicable_reason: str | None
    problem_id: str | None = Field(default=None, exclude=True)
    entities: list[ExperimentEntity] = Field(..., min_length=1)
    design: ExperimentDesign
    interventions: list[Intervention]
    environment: list[NamedValue] = Field(..., min_length=1)
    procedures: list[ProcedureStep] = Field(..., min_length=1)
    measurements: list[Measurement] = Field(..., min_length=1)
    data_product: DataProduct
    feasibility_constraints: FeasibilityConstraints

    @model_validator(mode="after")
    def validate_references(self) -> "ExperimentRequest":
        if bool(self.hypothesis) == bool(self.hypothesis_not_applicable_reason):
            raise ValueError(
                "provide exactly one of hypothesis or hypothesis_not_applicable_reason"
            )
        entity_ids = {entity.id for entity in self.entities}
        if len(entity_ids) != len(self.entities):
            raise ValueError("entity IDs must be unique")
        group_ids = {group.id for group in self.design.groups}
        if len(group_ids) != len(self.design.groups):
            raise ValueError("group IDs must be unique")
        unknown_entities = {
            ref
            for group in self.design.groups
            for ref in group.entity_ids
            if ref not in entity_ids
        }
        unknown_entities.update(
            ref
            for step in self.procedures
            for ref in step.entity_ids
            if ref not in entity_ids
        )
        unknown_entities.update(
            ref
            for measurement in self.measurements
            for ref in measurement.target_entity_ids
            if ref not in entity_ids
        )
        unknown_agents = {
            item.agent_entity_id
            for item in self.interventions
            if item.agent_entity_id and item.agent_entity_id not in entity_ids
        }
        unknown_groups = {
            ref
            for item in self.interventions
            for ref in item.target_group_ids
            if ref not in group_ids
        }
        if unknown_entities or unknown_agents:
            raise ValueError(
                f"unknown entity references: {sorted(unknown_entities | unknown_agents)}"
            )
        if unknown_groups:
            raise ValueError(f"unknown group references: {sorted(unknown_groups)}")
        control_refs = {ref for ref in self.design.controls if ref in group_ids}
        if (
            self.design.design_type in {"controlled", "factorial", "dose_response"}
            and not control_refs
        ):
            raise ValueError("controlled designs must reference at least one control group")
        orders = [step.order for step in self.procedures]
        if len(orders) != len(set(orders)):
            raise ValueError("procedure step order values must be unique")
        return self

    def matching_text(self) -> str:
        parts = [self.title, self.domain, self.objective, self.hypothesis or ""]
        for entity in self.entities:
            parts.extend([entity.name, entity.kind, entity.role, *entity.identifiers])
            parts.extend(f"{prop.name} {prop.value} {prop.unit or ''}" for prop in entity.properties)
        for factor in self.design.factors:
            parts.append(factor.name)
            parts.extend(f"{level.name} {level.value} {level.unit or ''}" for level in factor.levels)
        for intervention in self.interventions:
            parts.extend([intervention.manipulation, intervention.route_or_method, intervention.timing])
        for measurement in self.measurements:
            parts.extend(
                [
                    measurement.property,
                    measurement.method,
                    measurement.instrument_or_assay,
                    measurement.unit,
                    *measurement.timepoints,
                ]
            )
        return " ".join(str(part) for part in parts if part).strip()

    def as_dataset_request(self) -> "DatasetRequest":
        return DatasetRequest(
            question=self.matching_text(),
            problem_id=self.problem_id,
            structured_experiment=True,
            experiment=self.model_dump(exclude={"problem_id"}),
            desired_modalities=[
                measurement.instrument_or_assay for measurement in self.measurements
            ],
            desired_columns=[field.name for field in self.data_product.fields],
            max_rows=self.data_product.max_rows,
            max_bytes=self.data_product.max_bytes,
        )


class ValidationCheck(StrictModel):
    category: Literal[
        "completeness",
        "consistency",
        "measurability",
        "controls",
        "replication",
        "resources",
        "safety_ethics",
        "plausibility",
        "restricted",
    ]
    severity: Literal["info", "warning", "error"]
    path: str
    message: str


class ExperimentValidation(StrictModel):
    status: Literal["feasible", "needs_revision", "unrealistic", "restricted"]
    summary: str
    checks: list[ValidationCheck] = Field(default_factory=list)


class DatasetRequest(BaseModel):
    """Internal adapter from a validated experiment to the legacy curation boundary."""

    question: str = Field(
        ...,
        description="Natural-language description of the data the UEA wants collected or generated.",
    )
    problem_id: str | None = Field(
        default=None,
        description="Usually omitted by the UEA; supplied by the benchmark harness when needed.",
    )
    structured_experiment: bool = Field(default=False, exclude=True)
    experiment: dict[str, Any] | None = Field(default=None, exclude=True)
    desired_modalities: list[str] = Field(default_factory=list)
    desired_columns: list[str] = Field(
        default_factory=list,
        description=(
            "Exact tabular columns requested by the UEA. When supplied, the grant must "
            "contain only these columns (subject to format support) or be denied."
        ),
    )
    max_rows: int | None = Field(
        default=None,
        ge=1,
        description="Optional maximum number of rows to grant from each matching table.",
    )
    max_bytes: int = Field(default=1_000_000_000, ge=1_000_000)


class CatalogEntry(BaseModel):
    """One logical, grantable (or explicitly blocked) dataset for a problem.

    This is hidden, host-only benchmark metadata. The UEA never sees `source_paths`,
    `online`, or `reason`; only a neutral public view (id/description/kind/modalities).
    """

    id: str
    description: str = Field(..., description="Neutral description shown to the experiment-agent matcher.")
    kind: Literal["raw", "processed", "derivable", "online"] = "raw"
    grantable: bool = True
    source_paths: list[str] = Field(
        default_factory=list,
        description=(
            "Glob patterns relative to `data/` by default. Set `source_base` to "
            "`problem` for carefully curated host-only assets outside data/."
        ),
    )
    source_base: Literal["data", "problem"] = Field(
        default="data",
        description="Base directory for source_paths. UEA never sees this value.",
    )
    online: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Online source spec, e.g. {provider: zenodo|figshare|dryad|url, "
            "record_id|article_id|version_id|url: ...}."
        ),
    )
    modalities: list[str] = Field(default_factory=list)
    approx_bytes: int | None = None
    reason: str | None = Field(default=None, description="Why a non-grantable entry is blocked.")
    notes: str | None = None

    def public_view(self) -> dict[str, Any]:
        """Agent/UEA-facing projection that never leaks host paths or block reasons."""
        return {
            "description": self.description,
            "kind": self.kind,
            "modalities": self.modalities,
            "approx_bytes": self.approx_bytes,
        }


class DataCatalog(BaseModel):
    problem_id: str
    entries: list[CatalogEntry] = Field(default_factory=list)

    def grantable(self) -> list[CatalogEntry]:
        return [e for e in self.entries if e.grantable]

    def by_id(self, entry_id: str) -> CatalogEntry | None:
        for entry in self.entries:
            if entry.id == entry_id:
                return entry
        return None

    def public_id_for(self, entry_id: str) -> str | None:
        for idx, entry in enumerate(self.grantable(), start=1):
            if entry.id == entry_id:
                return f"dataset_{idx:03d}"
        return None

    def by_public_id(self, public_id: str) -> CatalogEntry | None:
        for idx, entry in enumerate(self.grantable(), start=1):
            if public_id == f"dataset_{idx:03d}":
                return entry
        return None

    def by_id_or_public_id(self, entry_id: str) -> CatalogEntry | None:
        return self.by_id(entry_id) or self.by_public_id(entry_id)

    def public_view(self) -> list[dict[str, Any]]:
        public_entries = []
        for idx, entry in enumerate(self.grantable(), start=1):
            view = entry.public_view()
            view["id"] = f"dataset_{idx:03d}"
            public_entries.append(view)
        return public_entries


class GrantedFile(BaseModel):
    source_path: str = Field(exclude=True)
    sandbox_path: str
    bytes: int
    reason: str


class DatasetGrant(BaseModel):
    request_id: str
    status: Literal["granted", "partial", "denied"]
    message: str
    denial_category: Literal[
        "restricted_request",
        "too_broad",
        "no_exact_match",
        "asset_unavailable",
        "policy_blocked",
    ] | None = Field(
        default=None,
        description=(
            "Stable, non-sensitive reason category that helps the UEA repair a denied "
            "request without revealing hidden catalog contents."
        ),
    )
    denial_reason: str | None = Field(
        default=None,
        exclude=True,
        description="Non-leaky policy reason when a request is denied before files are granted.",
    )
    files: list[GrantedFile] = Field(default_factory=list)
    rejected: list[str] = Field(
        default_factory=list,
        description="Human-readable notes about items withheld by the leak guard or policy.",
    )
    manifest_path: str | None = None


class ExperimentResult(StrictModel):
    request_id: str
    validation: ExperimentValidation
    execution_status: Literal[
        "completed",
        "partially_completed",
        "could_not_execute",
        "not_attempted",
    ]
    message: str
    files: list[GrantedFile] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    manifest_path: str | None = None


class ProblemSpec(BaseModel):
    problem_id: str
    benchmark_status: Literal["active", "conditional", "acquisition_only"] = "active"
    readiness_reason: str | None = None
    title: str
    doi: str
    sandbox_prompt: str
    expected_conclusions: list[str]
    judge_rubric: list[str]
    expected_caveats: list[str] = Field(default_factory=list)
    target_footprint_date: date | None = Field(
        default=None,
        description="Earliest known public target-lineage footprint; lineage is blocked regardless of chronology.",
    )
    external_source_cutoff: datetime | None = Field(
        default=None,
        description="Strict latest admissible publication time for independent external sources.",
    )
    # Optional extra identifiers used by the leak guard to detect that the UEA
    # found the original paper/repo. Hidden, host-only.
    leak_markers: list[str] = Field(default_factory=list)


class JudgeInput(BaseModel):
    problem_id: str
    final_answer: str
    transcript: str | None = None
    artifact_paths: list[Path] = Field(default_factory=list)


class EvidenceCitation(BaseModel):
    source: Literal["transcript", "final_answer", "artifact"]
    evidence_kind: Literal[
        "command_output",
        "data_excerpt",
        "analysis_result",
        "final_claim",
        "artifact",
    ]
    quote: str = ""
    artifact_path: str | None = None
    verified: bool = False


class ConclusionScore(BaseModel):
    conclusion: str = ""
    status: Literal["matched", "partial", "missing", "wrong"] = "missing"
    evidence: str = ""
    citations: list[EvidenceCitation] = Field(default_factory=list)
    evidence_verified: bool = False


class CaveatScore(BaseModel):
    caveat: str = ""
    status: Literal["addressed", "partial", "missing"] = "missing"
    citations: list[EvidenceCitation] = Field(default_factory=list)
    evidence_verified: bool = False


class JudgeResult(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    verdict: Literal["pass", "borderline", "fail"] = "fail"
    per_conclusion: list[ConclusionScore] = Field(default_factory=list)
    per_caveat: list[CaveatScore] = Field(default_factory=list)
    matched_conclusions: list[str] = Field(default_factory=list)
    missing_or_wrong: list[str] = Field(default_factory=list)
    caveats_addressed: list[str] = Field(default_factory=list)
    conclusion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    caveat_score: float = Field(default=0.0, ge=0.0, le=1.0)
    execution_score: float = Field(default=0.0, ge=0.0, le=1.0)
    analysis_manifest_verified: bool = False
    evidence_validation: list[str] = Field(default_factory=list)
    scoring_version: str = "deterministic-v1"
    leakage_suspected: bool = False
    leakage_rationale: str = ""
    rationale: str = ""
