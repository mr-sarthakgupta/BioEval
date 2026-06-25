from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from bioeval.bedrock_client import (
    DEFAULT_BEDROCK_API_BASE,
    create_bedrock_client,
    ensure_bedrock_bearer_token,
    messages_with_cache_point,
    prompt_cache_point,
    extract_text_from_response,
)
from bioeval.bedrock_cost import BedrockCostTracker
from bioeval.problems import load_problem_spec
from bioeval.run_record import append_jsonl, utc_now, write_json
from bioeval.schemas import JudgeResult


DEFAULT_JUDGE_MODEL = "us.anthropic.claude-sonnet-4-6"

JUDGE_SYSTEM_PROMPT = """You are a strict scientific-discovery benchmark judge.

You compare an under-eval-agent's (UEA) final answer against hidden expected
conclusions from the original research paper. The UEA never saw the paper; it had a
general problem statement, internet access, and a guarded data-agent.

Score each expected conclusion independently:
- "matched": the answer clearly states this conclusion with correct directionality
  and the transcript shows data analysis, quantitative reasoning, or explicit evidence
  that supports it.
- "partial": the right idea is present but vague, hedged, weakly supported, or not
  fully traced to evidence.
- "missing": not addressed.
- "wrong": addressed with the opposite or contradicted claim.

Scoring guidance:
- Do not reward name-dropping or generic domain knowledge that does not distinguish
  the specific finding.
- Do not mark a conclusion "matched" from final-answer prose alone. The evidence field
  must identify the analysis step, data source, or transcript evidence that supports it.
- Reward correct hypotheses, correct directionality, appropriate methods, quantified
  comparisons where relevant, and honest caveats. Credit addressing the expected caveats.
- Compute an overall `score` in [0,1] roughly as the fraction of expected conclusions
  matched (count "partial" as ~0.5), lightly adjusted for caveats and rigor.
- Verdict thresholds: pass >= 0.75, borderline >= 0.5, else fail.

Leakage check:
- If the answer reproduces paper-specific identifiers verbatim (exact title, DOI,
  author names, repository name, or oddly specific numeric results that could only
  come from reading the paper rather than from the granted data), set
  `leakage_suspected` true and explain in `leakage_rationale`. This flags a likely
  blind-setup violation. Leakage is disqualifying: set `verdict` to "fail" and keep
  `score` at or below 0.25 even if the scientific claims are otherwise correct.

Return ONLY JSON matching the provided output_schema.
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
    api_base: str,
    log_dir: Path | None = None,
) -> JudgeResult:
    ensure_bedrock_bearer_token()
    if not os.environ.get("AWS_BEARER_TOKEN_BEDROCK") and not os.environ.get("AWS_PROFILE"):
        raise RuntimeError(
            "Bedrock credentials required for judging. Set AWS_BEARER_TOKEN_BEDROCK or "
            "an ABSK... aws_session_token in ~/.aws/credentials."
        )

    spec = load_problem_spec(problem_id)
    user_payload = {
        "task": "anonymized_biology_discovery_task",
        "output_schema": JUDGE_JSON_SCHEMA,
        "hidden_expected_conclusions": spec.expected_conclusions,
        "hidden_expected_caveats": spec.expected_caveats,
        "hidden_judge_rubric": spec.judge_rubric,
        "hidden_leak_markers": [spec.title, spec.doi, *spec.leak_markers],
        "uea_final_answer": final_answer,
        "uea_transcript_excerpt": transcript[-40_000:] if transcript else None,
    }

    client = create_bedrock_client(api_base)
    system_blocks = [{"text": JUDGE_SYSTEM_PROMPT}]
    cache_point = prompt_cache_point()
    if cache_point:
        system_blocks.append(cache_point)

    messages = messages_with_cache_point(
        [{"role": "user", "content": [{"text": json.dumps(user_payload)}]}],
        cache_point,
    )

    cost_tracker = BedrockCostTracker(component="judge", model=model, log_dir=log_dir)
    response = client.converse(
        modelId=model.removeprefix("bedrock/"),
        system=system_blocks,
        messages=messages,
        inferenceConfig={
            "maxTokens": int(os.getenv("JUDGE_MAX_TOKENS", "8192")),
            "temperature": float(os.getenv("JUDGE_TEMPERATURE", "0")),
        },
    )
    cost_tracker.record(response.get("usage", {}) or {})
    cost_tracker.finalize()

    text = extract_text_from_response(response)
    result = JudgeResult.model_validate(parse_json_object(text))
    if result.leakage_suspected:
        result.score = min(result.score, 0.25)
        result.verdict = "fail"
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Judge a UEA answer against hidden paper conclusions.")
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--final-answer-file", type=Path, required=True)
    parser.add_argument("--transcript-file", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    parser.add_argument(
        "--api-base",
        default=os.getenv("JUDGE_API_BASE", DEFAULT_BEDROCK_API_BASE),
    )
    parser.add_argument("--run-id", default=os.getenv("BIOEVAL_RUN_ID"))
    parser.add_argument("--output-file", type=Path)
    parser.add_argument("--score-log", type=Path)
    return parser


def main() -> None:
    load_dotenv()
    args = build_arg_parser().parse_args()
    output_file = args.output_file or (args.final_answer_file.parent / "judge_result.json")
    log_dir = output_file.parent.parent / "logs" if output_file.parent.name == "results" else output_file.parent

    result = judge_with_llm(
        problem_id=args.problem_id,
        final_answer=args.final_answer_file.read_text(errors="replace"),
        transcript=read_optional(args.transcript_file),
        model=args.model,
        api_base=args.api_base,
        log_dir=log_dir,
    )
    result_dict = result.model_dump()
    record = {
        "event": "judge_result",
        "timestamp": utc_now(),
        "run_id": args.run_id,
        "problem_id": args.problem_id,
        "judge_model": args.model,
        "judge_api_base": args.api_base,
        "final_answer_file": str(args.final_answer_file),
        "transcript_file": str(args.transcript_file),
        "result": result_dict,
    }

    score_log = args.score_log or (args.final_answer_file.parent / "score_history.jsonl")
    write_json(output_file, record)
    append_jsonl(score_log, record)
    print(json.dumps(result_dict, indent=2))
    print(f"Saved judge result to {output_file}", file=sys.stderr)


if __name__ == "__main__":
    main()
