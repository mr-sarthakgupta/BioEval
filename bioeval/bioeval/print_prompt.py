from __future__ import annotations

import argparse

from bioeval.problems import load_problem_spec


def main() -> None:
    parser = argparse.ArgumentParser(description="Print the UEA-visible prompt for a problem.")
    parser.add_argument("--problem-id", required=True)
    args = parser.parse_args()
    spec = load_problem_spec(args.problem_id)
    print(spec.sandbox_prompt.strip())
    print()
    print("Available tools:")
    print("  read_file PATH [--line-start N --line-end M]   Read a workspace file.")
    print("  search PATTERN [--file-glob GLOB]              Regex search workspace files.")
    print(
        "  design_experiment '<complete ExperimentRequest JSON>'  Validate a reproducible "
        "experiment and obtain compatible data."
    )
    print("  web_search QUERY                               Search web with blind-setup blocks and academic fallback.")
    print("  research_papers search --query QUERY           Search scientific literature metadata.")
    print("  research_papers snippet_search --query QUERY   Search paper abstract excerpts with fallback.")
    print("  fetch_webpage URL                              Fetch allowed pages into reference/.")
    print("  run_command COMMAND                            Run filesystem-isolated analysis commands.")
    print("  check_space            Show disk usage against your budget.")
    print('  record_event --type note --text "..."   Optional annotation for important observations.')
    print('  submit_answer --text "..." --transcript analysis.log   Submit your final answer.')
    print()
    print("Important constraints:")
    print("- You do not have access to the original paper, paper repository, or answer key.")
    print("- Submit one fully structured experiment; free-form data inventory requests are unavailable.")
    print("- Revision or infeasibility stops before experiment execution.")
    print("- Do not request the original paper, DOI, repository, author code, solution, or answer key.")
    print("- Web/literature tools block direct paper/repository/DOI retrieval; use them for background methods.")
    print("- File and command tools are pinned to /workspace and are recorded automatically.")
    print("- Specify exact output fields and row/byte limits in the experiment data product.")
    print("- Run `check_space` before requesting or generating large files; you have a fixed disk budget.")
    print("- Installed: Python 3.11 with pandas/numpy/scipy/statsmodels/sklearn/lifelines, plus Rscript and common CLI readers.")
    print("- run_command uses a credential-free Landlock sandbox; pipes, interpreters, package installs, network access, and paths outside /workspace are blocked.")
    print("- Keep an analysis log with experiment designs, commands, results, and reasoning.")
    print("- Shell I/O, shell commands, and BioEval tool calls are recorded automatically.")
    print("- Use `record_event` only for high-level observations, hypotheses, and decisions.")
    print("- When you are confident in your conclusions, call `submit_answer` with that transcript.")
