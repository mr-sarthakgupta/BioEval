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
    print(
        '  request_data "Describe the measurement, dataset, or public data you want" '
        "[--modality csv --max-bytes 200000000]"
    )
    print("  check_space            Show disk usage against your budget.")
    print('  submit_answer --text "..."   (or --file answer.md)   Submit your final answer.')
    print()
    print("Important constraints:")
    print("- You do not have access to the original paper, paper repository, or answer key.")
    print("- Ask the data-agent for data as if experiments or public datasets must be obtained on demand.")
    print("- The data-agent may grant subsets of large datasets; ask for specific rows/columns if needed.")
    print("- Run `check_space` before requesting or generating large files; you have a fixed disk budget.")
    print("- When you are confident in your conclusions, call `submit_answer`.")
