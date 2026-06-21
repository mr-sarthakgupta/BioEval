#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

from bioeval_tool_common import append_tool_event, relative_workspace_path, truncate, workspace_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Read a file inside /workspace.")
    parser.add_argument("path")
    parser.add_argument("--line-start", type=int, default=1)
    parser.add_argument("--line-end", type=int)
    parser.add_argument("--max-chars", type=int, default=20000)
    args = parser.parse_args()
    request = vars(args)
    try:
        path = workspace_path(args.path)
        if not path.is_file():
            raise ValueError("path is not a file")
        lines = path.read_text(errors="replace").splitlines()
        start = max(args.line_start, 1)
        end = args.line_end or len(lines)
        selected = lines[start - 1:end]
        rendered = "\n".join(f"{idx}|{line}" for idx, line in enumerate(selected, start=start))
        rendered = truncate(rendered, args.max_chars)
        response = {
            "path": relative_workspace_path(path),
            "line_start": start,
            "line_end": min(end, len(lines)),
            "total_lines": len(lines),
            "content": rendered,
        }
        append_tool_event("read_file", request, response, "ok")
        print(rendered)
        return 0
    except Exception as exc:
        response = {"error": str(exc)}
        append_tool_event("read_file", request, response, "error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
