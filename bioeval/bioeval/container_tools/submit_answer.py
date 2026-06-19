#!/usr/bin/env python3
"""Submit the UEA's final answer from inside the sandbox.

Writes the final answer (and an optional analysis transcript) to the host-mounted
submit directory, where `bioeval-judge` can score it. This is how the UEA ends a run.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit your final answer for judging.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Final answer text.")
    src.add_argument("--file", type=Path, help="Path to a file containing the final answer.")
    parser.add_argument("--transcript", type=Path, help="Optional analysis log to include.")
    parser.add_argument(
        "--submit-dir",
        default=os.getenv("BIOEVAL_SUBMIT_DIR", "/submit"),
        help="Where to write outputs (host-mounted).",
    )
    args = parser.parse_args()

    submit_dir = Path(args.submit_dir)
    try:
        submit_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Cannot write to submit dir {submit_dir}: {exc}", file=sys.stderr)
        return 1

    answer = args.text if args.text is not None else args.file.read_text(errors="replace")
    (submit_dir / "final_answer.txt").write_text(answer)
    if args.transcript and args.transcript.exists():
        (submit_dir / "transcript.txt").write_text(args.transcript.read_text(errors="replace"))

    print(f"Submitted final answer to {submit_dir / 'final_answer.txt'}.")
    print("The benchmark operator can now run bioeval-judge on this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
