from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class DatasetRequest(BaseModel):
    """Request made by the under-eval agent through the data-agent tool."""

    question: str = Field(
        ...,
        description="Natural-language description of the data the UEA wants collected or generated.",
    )
    problem_id: str | None = Field(
        default=None,
        description="Usually omitted by the UEA; supplied by the benchmark harness when needed.",
    )
    desired_modalities: list[str] = Field(default_factory=list)
    max_bytes: int = Field(default=200_000_000, ge=1_000_000)


class CatalogEntry(BaseModel):
    """One logical, grantable (or explicitly blocked) dataset for a problem.

    This is hidden, host-only benchmark metadata. The UEA never sees `source_paths`,
    `online`, or `reason`; only a neutral public view (id/description/kind/modalities).
    """

    id: str
    description: str = Field(..., description="Neutral description shown to the data-agent / UEA.")
    kind: Literal["raw", "processed", "derivable", "online"] = "raw"
    grantable: bool = True
    source_paths: list[str] = Field(
        default_factory=list,
        description="Glob patterns relative to the problem's data/ directory.",
    )
    online: dict[str, Any] | None = Field(
        default=None,
        description="Online source spec, e.g. {provider: zenodo|figshare|url, record_id|article_id|url: ...}.",
    )
    modalities: list[str] = Field(default_factory=list)
    approx_bytes: int | None = None
    reason: str | None = Field(default=None, description="Why a non-grantable entry is blocked.")
    notes: str | None = None

    def public_view(self) -> dict[str, Any]:
        """Agent/UEA-facing projection that never leaks host paths or block reasons."""
        return {
            "id": self.id,
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

    def public_view(self) -> list[dict[str, Any]]:
        return [e.public_view() for e in self.grantable()]


class GrantedFile(BaseModel):
    source_path: str
    sandbox_path: str
    bytes: int
    reason: str


class DatasetGrant(BaseModel):
    request_id: str
    status: Literal["granted", "partial", "denied"]
    message: str
    files: list[GrantedFile] = Field(default_factory=list)
    rejected: list[str] = Field(
        default_factory=list,
        description="Human-readable notes about items withheld by the leak guard or policy.",
    )
    manifest_path: str | None = None


class ProblemSpec(BaseModel):
    problem_id: str
    title: str
    doi: str
    sandbox_prompt: str
    expected_conclusions: list[str]
    judge_rubric: list[str]
    expected_caveats: list[str] = Field(default_factory=list)
    # Optional extra identifiers used by the leak guard to detect that the UEA
    # found the original paper/repo. Hidden, host-only.
    leak_markers: list[str] = Field(default_factory=list)


class JudgeInput(BaseModel):
    problem_id: str
    final_answer: str
    transcript: str | None = None
    artifact_paths: list[Path] = Field(default_factory=list)


class ConclusionScore(BaseModel):
    conclusion: str = ""
    status: Literal["matched", "partial", "missing", "wrong"] = "missing"
    evidence: str = ""


class JudgeResult(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    verdict: Literal["pass", "borderline", "fail"] = "fail"
    per_conclusion: list[ConclusionScore] = Field(default_factory=list)
    matched_conclusions: list[str] = Field(default_factory=list)
    missing_or_wrong: list[str] = Field(default_factory=list)
    caveats_addressed: list[str] = Field(default_factory=list)
    leakage_suspected: bool = False
    leakage_rationale: str = ""
    rationale: str = ""
