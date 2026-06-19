from __future__ import annotations

from pathlib import Path

import yaml

from bioeval.schemas import ProblemSpec


SPEC_DIR = Path(__file__).parent / "problem_specs"


def list_problem_specs(spec_dir: Path = SPEC_DIR) -> list[ProblemSpec]:
    specs: list[ProblemSpec] = []
    for path in sorted(spec_dir.glob("*.yaml")):
        specs.append(ProblemSpec.model_validate(yaml.safe_load(path.read_text())))
    return specs


def load_problem_spec(problem_id: str, spec_dir: Path = SPEC_DIR) -> ProblemSpec:
    for spec in list_problem_specs(spec_dir):
        if spec.problem_id == problem_id:
            return spec
    raise KeyError(f"Unknown problem_id: {problem_id}")
