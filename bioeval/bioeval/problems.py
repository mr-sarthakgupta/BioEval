from __future__ import annotations

from pathlib import Path

import yaml

from bioeval.schemas import ProblemSpec
from bioeval.catalog import load_catalog, resolve_entry_files


SPEC_DIR = Path(__file__).parent / "problem_specs"


def resolve_problem_root(problem_id: str, repo_root: Path | None = None) -> Path | None:
    root = repo_root or Path(__file__).resolve().parents[2]
    for folder in ("problems_complete", "problems_imcomplete"):
        candidate = root / folder / problem_id
        if candidate.is_dir():
            return candidate
    return None


def resolve_problems_dir(problem_id: str, repo_root: Path | None = None) -> str | None:
    problem_root = resolve_problem_root(problem_id, repo_root)
    return problem_root.parent.name if problem_root is not None else None


def list_problem_specs(spec_dir: Path = SPEC_DIR) -> list[ProblemSpec]:
    specs: list[ProblemSpec] = []
    seen: set[str] = set()
    for path in sorted(spec_dir.glob("*.yaml")):
        spec = ProblemSpec.model_validate(yaml.safe_load(path.read_text()))
        if spec.problem_id in seen:
            raise ValueError(f"Duplicate problem_id in problem specs: {spec.problem_id}")
        seen.add(spec.problem_id)
        specs.append(spec)
    return specs


def load_problem_spec(problem_id: str, spec_dir: Path = SPEC_DIR) -> ProblemSpec:
    for spec in list_problem_specs(spec_dir):
        if spec.problem_id == problem_id:
            return spec
    raise KeyError(f"Unknown problem_id: {problem_id}")


def validate_problem_ready(spec: ProblemSpec, repo_root: Path) -> list[str]:
    problem_root = resolve_problem_root(spec.problem_id, repo_root)
    if problem_root is None:
        return ["problem directory is missing"]
    try:
        catalog = load_catalog(problem_root)
    except (FileNotFoundError, ValueError) as exc:
        return [str(exc)]
    reasons: list[str] = []
    for entry in catalog.entries:
        if not entry.grantable:
            continue
        if entry.online is None and not resolve_entry_files(problem_root, entry):
            reasons.append(f"grantable catalog entry has no available files: {entry.id}")
    return reasons
