from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from bioeval.problems import load_problem_spec
from bioeval.schemas import JudgeResult


JUDGE_SYSTEM_PROMPT = """You are a strict scientific-discovery benchmark judge.

You compare an under-eval-agent's (UEA) final answer against hidden expected
conclusions from the original research paper. The UEA never saw the paper; it had a
general problem statement, internet access, and a guarded data-agent.

Score each expected conclusion independently:
- "matched": the answer clearly states this conclusion with correct directionality
  and adequate support.
- "partial": the right idea is present but vague, hedged, or weakly supported.
- "missing": not addressed.
- "wrong": addressed with the opposite or contradicted claim.

Scoring guidance:
- Do not reward name-dropping or generic domain knowledge that does not distinguish
  the specific finding.
- Reward correct hypotheses, correct directionality, appropriate methods, and honest
  caveats. Credit addressing the expected caveats.
- Compute an overall `score` in [0,1] roughly as the fraction of expected conclusions
  matched (count "partial" as ~0.5), lightly adjusted for caveats and rigor.
- Verdict thresholds: pass >= 0.75, borderline >= 0.5, else fail.

Leakage check:
- If the answer reproduces paper-specific identifiers verbatim (exact title, DOI,
  author names, repository name, or oddly specific numeric results that could only
  come from reading the paper rather than from the granted data), set
  `leakage_suspected` true and explain in `leakage_rationale`. This flags a likely
  blind-setup violation; still score the science on its merits.

Return ONLY JSON matching the provided schema.
"""


JUDGE_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "score": {"type": "number", "minimum": 0, "maximum": 1},
        "verdict": {"type": "string", "enum": ["pass", "borderline", "fail"]},
        "per_conclusion": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "conclusion": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["matched", "partial", "missing", "wrong"],
                    },
                    "evidence": {"type": "string"},
                },
                "required": ["conclusion", "status", "evidence"],
            },
        },
        "matched_conclusions": {"type": "array", "items": {"type": "string"}},
        "missing_or_wrong": {"type": "array", "items": {"type": "string"}},
        "caveats_addressed": {"type": "array", "items": {"type": "string"}},
        "leakage_suspected": {"type": "boolean"},
        "leakage_rationale": {"type": "string"},
        "rationale": {"type": "string"},
    },
    "required": [
        "score",
        "verdict",
        "per_conclusion",
        "matched_conclusions",
        "missing_or_wrong",
        "caveats_addressed",
        "leakage_suspected",
        "leakage_rationale",
        "rationale",
    ],
}


def read_optional(path: Path | None) -> str | None:
    if not path:
        return None
    return path.read_text(errors="replace")


def parse_json_object(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def judge_with_llm(
    *,
    problem_id: str,
    final_answer: str,
    transcript: str | None,
    model: str,
) -> JudgeResult:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY must be set for LLM judging.")

    spec = load_problem_spec(problem_id)
    client = OpenAI()
    user_payload = {
        "problem_id": spec.problem_id,
        "hidden_expected_conclusions": spec.expected_conclusions,
        "hidden_expected_caveats": spec.expected_caveats,
        "hidden_judge_rubric": spec.judge_rubric,
        "hidden_leak_markers": [spec.title, spec.doi, *spec.leak_markers],
        "uea_final_answer": final_answer,
        "uea_transcript_excerpt": transcript[-40_000:] if transcript else None,
    }
    response = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "judge_result",
                "schema": JUDGE_JSON_SCHEMA,
                "strict": True,
            }
        },
    )
    return JudgeResult.model_validate(parse_json_object(response.output_text))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judge a UEA answer against hidden paper conclusions.")
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--final-answer-file", type=Path, required=True)
    parser.add_argument("--transcript-file", type=Path)
    parser.add_argument("--model", default=os.getenv("JUDGE_MODEL", "gpt-5.5"))
    return parser


def main() -> None:
    load_dotenv()
    args = build_arg_parser().parse_args()
    result = judge_with_llm(
        problem_id=args.problem_id,
        final_answer=args.final_answer_file.read_text(errors="replace"),
        transcript=read_optional(args.transcript_file),
        model=args.model,
    )
    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    main()
