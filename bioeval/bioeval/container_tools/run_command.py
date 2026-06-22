#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys

from bioeval_tool_common import WORKSPACE, append_tool_event, truncate


ALLOWED = {
    "python", "python3", "Rscript",
    "cat", "head", "tail", "wc", "grep", "rg", "find", "ls", "du", "df", "stat",
    "sort", "uniq", "cut", "awk", "sed", "tr", "paste", "join", "diff", "comm",
    "file", "which", "xxd", "jq", "tar", "unzip", "zipinfo", "echo", "printf", "date", "whoami",
    "uname", "env", "pwd",
}
BLOCKED = {
    "rm", "chmod", "chown", "sudo", "su", "curl", "wget", "scp", "rsync", "ssh",
    "nc", "kill", "pkill", "mv", "cp", "dd", "mkdir", "rmdir", "touch", "ln",
    "install", "apt", "apt-get", "pip", "npm", "conda",
}
SHELL_CONTROL_TOKENS = {"|", "||", "&", "&&", ";", ">", ">>", "<", "2>", "2>>"}
SHELL_SUBSTITUTION_PATTERNS = [re.compile(r"`"), re.compile(r"\$[({]")]


def safety_error(command: str) -> str | None:
    try:
        tokens = shlex.split(command)
    except ValueError as exc:
        return f"could not parse command: {exc}"
    if not tokens:
        return "empty command"
    for token in tokens:
        if token in SHELL_CONTROL_TOKENS or re.fullmatch(r"\d?>{1,2}", token):
            return "shell operators, redirects, substitutions, and pipelines are blocked"
    for pattern in SHELL_SUBSTITUTION_PATTERNS:
        if pattern.search(command):
            return "shell substitutions are blocked"
    exe = os.path.basename(tokens[0])
    if exe in BLOCKED:
        return f"'{exe}' is blocked"
    if exe not in ALLOWED:
        return f"'{exe}' is not allowed"
    for token in tokens[1:]:
        if token.startswith("/") and not token.startswith("/workspace"):
            return "absolute paths outside /workspace are blocked"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a constrained read-only command in /workspace.")
    parser.add_argument("command")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--max-chars", type=int, default=20000)
    args = parser.parse_args()
    request = vars(args)
    error = safety_error(args.command)
    if error:
        response = {"error": error}
        append_tool_event("run_command", request, response, "error")
        print(f"Error: {error}", file=sys.stderr)
        return 1
    try:
        result = subprocess.run(
            shlex.split(args.command),
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=max(1, min(args.timeout, 120)),
        )
        combined = result.stdout + (("\n[stderr]\n" + result.stderr) if result.stderr else "")
        output = truncate(combined or "(no output)", args.max_chars)
        response = {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        append_tool_event("run_command", request, response, "ok" if result.returncode == 0 else "error")
        print(f"$ {args.command}\n[exit code: {result.returncode}]\n\n{output}")
        return result.returncode
    except Exception as exc:
        response = {"error": str(exc)}
        append_tool_event("run_command", request, response, "error")
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
