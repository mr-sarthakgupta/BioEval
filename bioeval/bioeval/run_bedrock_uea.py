from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from dotenv import load_dotenv

from bioeval.problems import list_problem_specs, resolve_problems_dir


DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_API_BASE = "bedrock:us-east-1"


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def run(
    argv: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(argv), flush=True)
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        capture_output=capture,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if check and proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, argv, proc.stdout, proc.stderr)
    return proc


def compose_base(root: Path, env_file: Path) -> list[str]:
    cmd = ["docker", "compose"]
    if env_file.exists():
        cmd.extend(["--env-file", str(env_file)])
    cmd.extend(["-f", str(root / "docker" / "compose.yaml")])
    return cmd


def parse_init_output(output: str) -> tuple[str, Path]:
    run_id = None
    run_root = None
    for line in output.splitlines():
        if line.startswith("BIOEVAL_RUN_ID="):
            run_id = line.split("=", 1)[1].strip()
        elif line.startswith("BIOEVAL_RUN_ROOT="):
            run_root = Path(line.split("=", 1)[1].strip())
    if not run_id or run_root is None:
        raise RuntimeError("Could not parse bioeval-init-run output.")
    if not run_root.is_absolute():
        run_root = package_root() / run_root
    return run_id, run_root


def wait_for_experiment_agent(timeout: int = 120) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            with urlopen("http://127.0.0.1:8765/health", timeout=2) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001 - retry until timeout
            last_error = exc
        time.sleep(2)
    raise TimeoutError(f"experiment-agent did not become healthy: {last_error}")


def selected_problems(args: argparse.Namespace) -> list[str]:
    if args.all:
        statuses = {"active", "conditional"} if args.include_conditional else {"active"}
        return [
            spec.problem_id
            for spec in list_problem_specs()
            if spec.benchmark_status in statuses
        ]
    if args.problems:
        return args.problems
    raise SystemExit("Pass one or more problem IDs, or use --all.")


def prepare_run(problem_id: str, args: argparse.Namespace, root: Path, env: dict[str, str]) -> tuple[str, Path]:
    command = [
        sys.executable,
        "-m",
        "bioeval.init_run",
        "--problem-id",
        problem_id,
        "--uea-model",
        args.model,
    ]
    if args.include_conditional:
        command.append("--allow-conditional")
    init = run(
        command,
        cwd=root,
        env=env,
        capture=True,
    )
    run_id, run_root = parse_init_output(init.stdout)
    workspace_task = run_root / "uea_workspace" / "TASK.md"
    workspace_task.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_root / "TASK.md", workspace_task)
    return run_id, run_root


def run_problem(problem_id: str, args: argparse.Namespace, root: Path, env_file: Path) -> None:
    env = os.environ.copy()
    repo_root = root.parent
    problems_dir = resolve_problems_dir(problem_id, repo_root)
    if problems_dir is None:
        raise FileNotFoundError(f"No data catalog found for {problem_id}.")
    env.update(
        {
            "BIOEVAL_PROBLEM_ID": problem_id,
            "BIOEVAL_PROBLEMS_DIR": problems_dir,
            "UEA_BEDROCK_MODEL": args.model,
            "UEA_BEDROCK_API_BASE": args.api_base,
            "UEA_MODEL": args.model,
            "EXPERIMENT_AGENT_MODEL": os.environ.get("EXPERIMENT_AGENT_MODEL", DEFAULT_MODEL),
            "EXPERIMENT_AGENT_API_BASE": os.environ.get(
                "EXPERIMENT_AGENT_API_BASE", DEFAULT_API_BASE
            ),
            "AWS_REGION": os.environ.get("AWS_REGION", "us-east-1"),
            "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
            "BEDROCK_AWS_REGION": os.environ.get("BEDROCK_AWS_REGION", "us-east-1"),
            "BIOEVAL_STRICT_DATA_REQUESTS": os.environ.get("BIOEVAL_STRICT_DATA_REQUESTS", "1"),
            "BIOEVAL_MAX_DATASET_GRANTS_PER_REQUEST": os.environ.get(
                "BIOEVAL_MAX_DATASET_GRANTS_PER_REQUEST",
                "1",
            ),
        }
    )
    if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        env["AWS_BEARER_TOKEN_BEDROCK"] = os.environ["AWS_BEARER_TOKEN_BEDROCK"]

    run_id, run_root = prepare_run(problem_id, args, root, env)
    env["BIOEVAL_RUN_ID"] = run_id
    print(f"\n=== Running {problem_id} ({run_id}) ===", flush=True)

    compose = compose_base(root, env_file)
    started = False
    try:
        if not args.reuse_containers:
            run(compose + ["down"], cwd=root, env=env, check=False)

        up_cmd = compose + ["up", "-d"]
        if not args.no_build:
            up_cmd.append("--build")
        up_cmd.extend(["experiment-agent", "uea"])
        run(up_cmd, cwd=root, env=env)
        started = True
        wait_for_experiment_agent(timeout=args.health_timeout)

        agent_cmd = [
            "uea_bedrock_agent",
            "--task-file",
            "/workspace/TASK.md",
            "--model",
            args.model,
            "--api-base",
            args.api_base,
            "--max-steps",
            str(args.max_steps),
            "--max-tokens",
            str(args.max_tokens),
            "--temperature",
            str(args.temperature),
        ]
        run(compose + ["exec", "-T", "uea", *agent_cmd], cwd=root, env=env)
        if not args.skip_judge:
            final_answer = run_root / "results" / "final_answer.txt"
            transcript = run_root / "results" / "transcript.txt"
            if not final_answer.is_file() or not transcript.is_file():
                raise RuntimeError(
                    "UEA completed without the final answer and transcript required for judging."
                )
            judge_cmd = [
                sys.executable,
                "-m",
                "bioeval.judge",
                "--problem-id",
                problem_id,
                "--final-answer-file",
                str(final_answer),
                "--transcript-file",
                str(transcript),
                "--model",
                args.judge_model,
                "--api-base",
                args.judge_api_base,
                "--run-id",
                run_id,
            ]
            manifest = run_root / "results" / "analysis_manifest.json"
            if manifest.is_file():
                judge_cmd.extend(
                    [
                        "--analysis-manifest",
                        str(manifest),
                        "--artifact-root",
                        str(run_root / "results"),
                    ]
                )
            run(judge_cmd, cwd=root, env=env)
        print(f"Run artifacts: {run_root}", flush=True)
    finally:
        if started and not args.keep_up:
            run(compose + ["down"], cwd=root, env=env, check=False)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run selected BioEval problems with a Sonnet 4.6 UEA on AWS Bedrock."
    )
    parser.add_argument("problems", nargs="*", help="Problem IDs to run.")
    parser.add_argument("--all", action="store_true", help="Run all active problem specs.")
    parser.add_argument(
        "--include-conditional",
        action="store_true",
        help="Include conditional (but never acquisition-only) specs with --all.",
    )
    parser.add_argument("--model", default=os.getenv("UEA_BEDROCK_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-base", default=os.getenv("UEA_BEDROCK_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--max-steps", type=int, default=int(os.getenv("UEA_MAX_STEPS", "40")))
    parser.add_argument("--max-tokens", type=int, default=int(os.getenv("UEA_MAX_TOKENS", "8192")))
    parser.add_argument("--temperature", type=float, default=float(os.getenv("UEA_TEMPERATURE", "0.2")))
    parser.add_argument("--judge-model", default=os.getenv("JUDGE_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--judge-api-base",
        default=os.getenv("JUDGE_API_BASE", DEFAULT_API_BASE),
    )
    parser.add_argument(
        "--skip-judge",
        action="store_true",
        help="Do not automatically judge a successfully submitted run.",
    )
    parser.add_argument("--health-timeout", type=int, default=120)
    parser.add_argument("--no-build", action="store_true", help="Do not rebuild Docker images.")
    parser.add_argument("--keep-up", action="store_true", help="Leave Compose services running after completion.")
    parser.add_argument("--reuse-containers", action="store_true", help="Skip docker compose down before each run.")
    return parser


def main() -> None:
    root = package_root()
    env_file = root / ".env"
    load_dotenv(env_file)
    args = build_arg_parser().parse_args()
    for problem_id in selected_problems(args):
        run_problem(problem_id, args, root, env_file)


if __name__ == "__main__":
    main()
