#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import re
import sys

from bioeval_tool_common import WORKSPACE, append_tool_event, relative_workspace_path, truncate


def main() -> int:
    parser = argparse.ArgumentParser(description="Regex search inside /workspace.")
    parser.add_argument("pattern")
    parser.add_argument("--file-glob", default="*")
    parser.add_argument("--max-matches", type=int, default=200)
    parser.add_argument("--max-chars", type=int, default=20000)
    args = parser.parse_args()
    request = vars(args)
    try:
        regex = re.compile(args.pattern)
        rows: list[str] = []
        matches = 0
        for path in sorted(WORKSPACE.rglob("*")):
            if not path.is_file():
                continue
            rel = relative_workspace_path(path)
            if not fnmatch.fnmatch(rel, args.file_glob):
                continue
            try:
                lines = path.read_text(errors="replace").splitlines()
            except Exception:
                continue
            for idx, line in enumerate(lines, start=1):
                if regex.search(line):
                    rows.append(f"{rel}:{idx}:{line}")
                    matches += 1
                    if matches >= args.max_matches:
                        break
            if matches >= args.max_matches:
                break
        output = truncate("\n".join(rows) if rows else "No matches found.", args.max_chars)
        response = {"matches": matches, "content": output, "truncated_at_matches": matches >= args.max_matches}
        append_tool_event("search", request, response, "ok")
        print(output)
        return 0
    except Exception as exc:
        response = {"error": str(exc)}
        append_tool_event("search", request, response, "error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
