from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from bioeval.problems import (
    load_problem_spec,
    resolve_problems_dir,
    validate_problem_ready,
)
from bioeval.run_record import default_run_id, env_snapshot, git_commit, git_dirty, utc_now, write_json


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a recorded BioEval run directory.")
    parser.add_argument("--problem-id", default=os.getenv("BIOEVAL_PROBLEM_ID"), required=False)
    parser.add_argument("--run-id", default=os.getenv("BIOEVAL_RUN_ID"))
    parser.add_argument("--runs-root", type=Path, default=Path("runs"))
    parser.add_argument("--uea-model", default=os.getenv("UEA_MODEL"))
    parser.add_argument("--notes", default="")
    parser.add_argument("--allow-conditional", action="store_true")
    return parser


def main() -> None:
    load_dotenv()
    args = build_arg_parser().parse_args()
    if not args.problem_id:
        raise SystemExit("--problem-id or BIOEVAL_PROBLEM_ID is required")

    spec = load_problem_spec(args.problem_id)
    if spec.benchmark_status == "acquisition_only":
        raise SystemExit(
            f"{args.problem_id} is acquisition-only: {spec.readiness_reason or 'not runnable'}"
        )
    if spec.benchmark_status == "conditional" and not args.allow_conditional:
        raise SystemExit(
            f"{args.problem_id} is conditional; pass --allow-conditional after reviewing: "
            f"{spec.readiness_reason or 'readiness is incomplete'}"
        )
    repo_root = Path(__file__).resolve().parents[2]
    readiness_errors = validate_problem_ready(spec, repo_root)
    if readiness_errors:
        raise SystemExit(
            "Problem is not ready:\n- " + "\n- ".join(readiness_errors)
        )
    problems_dir = resolve_problems_dir(args.problem_id, repo_root)
    if problems_dir is None:
        raise SystemExit(f"Problem directory is missing: {args.problem_id}")
    run_id = args.run_id or default_run_id(args.problem_id)
    run_root = args.runs_root / args.problem_id / run_id
    for child in ["uea_workspace", "data_grants", "results", "logs"]:
        (run_root / child).mkdir(parents=True, exist_ok=True)

    metadata = {
        "run_id": run_id,
        "problem_id": args.problem_id,
        "created_at": utc_now(),
        "status": "initialized",
        "uea_model": args.uea_model,
        "notes": args.notes,
        "repo": {
            "root": str(repo_root),
            "commit": git_commit(repo_root),
            "dirty": git_dirty(repo_root),
        },
        "environment": env_snapshot(
            [
                "EXPERIMENT_AGENT_MODEL",
                "EXPERIMENT_AGENT_API_BASE",
                "UEA_BEDROCK_MODEL",
                "UEA_BEDROCK_API_BASE",
                "UEA_MAX_STEPS",
                "UEA_MAX_TOKENS",
                "BEDROCK_AWS_REGION",
                "AWS_REGION",
                "JUDGE_MODEL",
                "JUDGE_API_BASE",
                "BIOEVAL_DISK_BUDGET_GB",
                "BIOEVAL_MEM_LIMIT",
                "BIOEVAL_CPUS",
                "BIOEVAL_STRICT_DATA_REQUESTS",
                "BIOEVAL_MAX_DATASET_GRANTS_PER_REQUEST",
                "BIOEVAL_TRAFFIC_GUARD_ENABLED",
                "BIOEVAL_TRAFFIC_GUARD_FAIL_CLOSED",
                "BIOEVAL_TRAFFIC_GUARD_MODEL",
                "BIOEVAL_TRAFFIC_GUARD_API_BASE",
                "BIOEVAL_OPENALEX_DESCENDANT_DEPTH",
                "BIOEVAL_OPENALEX_DESCENDANT_MAX_NODES",
                "BIOEVAL_OPENALEX_GRAPH_CACHE_TTL",
            ]
        ),
        "prompt": {
            "title": spec.title,
            "sandbox_prompt": spec.sandbox_prompt.strip(),
        },
        "paths": {
            "problems_dir": problems_dir,
            "run_root": str(run_root),
            "workspace": str(run_root / "uea_workspace"),
            "data_grants": str(run_root / "data_grants"),
            "results": str(run_root / "results"),
            "logs": str(run_root / "logs"),
        },
    }
    write_json(run_root / "run_metadata.json", metadata)
    (run_root / "TASK.md").write_text(spec.sandbox_prompt.strip() + "\n", encoding="utf-8")

    print(f"BIOEVAL_RUN_ID={run_id}")
    print(f"BIOEVAL_RUN_ROOT={run_root}")
    print(f"Run metadata: {run_root / 'run_metadata.json'}")
    print()
    print("Use this run with Docker Compose:")
    print(f"  export BIOEVAL_RUN_ID={run_id}")
    print(f"  export BIOEVAL_PROBLEM_ID={args.problem_id}")
    print(f"  export BIOEVAL_PROBLEMS_DIR={problems_dir}")


if __name__ == "__main__":
    main()
