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
        '  request_data "Specifically name the measurement/data type and scope you want" '
        "[--modality csv --max-bytes 200000000]"
    )
    print("  web_search QUERY                               Search web with blind-setup blocks and academic fallback.")
    print("  research_papers search --query QUERY           Search scientific literature metadata.")
    print("  research_papers snippet_search --query QUERY   Search paper passages with fallback.")
    print("  fetch_webpage URL                              Fetch allowed pages into reference/.")
    print("  run_command COMMAND                            Run constrained read-only commands.")
    print("  check_space            Show disk usage against your budget.")
    print('  record_event --type note --text "..."   Optional annotation for important observations.')
    print('  submit_answer --text "..." --transcript analysis.log   Submit your final answer.')
    print()
    print("Important constraints:")
    print("- You do not have access to the original paper, paper repository, or answer key.")
    print("- Ask the data-agent for data as if experiments or public datasets must be obtained on demand.")
    print("- Data requests must be specific; broad 'do you have any/all data?' requests may be denied.")
    print("- Do not request the original paper, DOI, repository, author code, solution, or answer key.")
    print("- Web/literature tools block direct paper/repository/DOI retrieval; use them for background methods.")
    print("- File and command tools are pinned to /workspace and are recorded automatically.")
    print("- The data-agent may grant subsets of large datasets; ask for specific rows/columns if needed.")
    print("- Run `check_space` before requesting or generating large files; you have a fixed disk budget.")
    print("- Installed: Python 3.11 with pandas/numpy/scipy/statsmodels/sklearn/lifelines, plus Rscript and common CLI readers.")
    print("- run_command does not invoke a shell; pipes, redirects, substitutions, package installs, and destructive commands are blocked.")
    print("- Keep an analysis log with data requests, commands, results, and reasoning.")
    print("- Shell I/O, shell commands, and BioEval tool calls are recorded automatically.")
    print("- Use `record_event` only for high-level observations, hypotheses, and decisions.")
    print("- When you are confident in your conclusions, call `submit_answer` with that transcript.")
