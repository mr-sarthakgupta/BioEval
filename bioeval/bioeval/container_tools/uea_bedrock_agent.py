#!/usr/bin/env python3
"""Run an agent-under-evaluation inside the sandbox with AWS Bedrock Converse."""

from __future__ import annotations

import argparse
import configparser
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bedrock_cost import BedrockCostTracker


DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-6"
DEFAULT_API_BASE = "bedrock:us-east-1"
WORKSPACE = Path("/workspace")
TRANSCRIPT = WORKSPACE / "uea_bedrock_transcript.md"
TRACE = WORKSPACE / "uea_bedrock_trace.json"
FINAL_ANSWER = WORKSPACE / "final_answer.md"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def region_from_api_base(api_base: str | None) -> str | None:
    if api_base and api_base.startswith("bedrock:"):
        return api_base.split(":", 1)[1] or None
    return None


def bedrock_api_key_from_aws_credentials(
    profile: str | None = None,
    credentials_path: Path | None = None,
) -> str | None:
    credentials_path = credentials_path or Path(
        os.environ.get("AWS_SHARED_CREDENTIALS_FILE", Path.home() / ".aws" / "credentials")
    )
    if not credentials_path.exists():
        return None

    parser = configparser.RawConfigParser()
    parser.read(credentials_path)
    section = profile or os.environ.get("AWS_PROFILE") or "default"
    if not parser.has_section(section):
        return None

    token = parser.get(section, "aws_session_token", fallback="").strip()
    if token.startswith("ABSK"):
        return token
    return None


def ensure_bedrock_bearer_token(profile: str | None = None) -> None:
    if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        return
    token = bedrock_api_key_from_aws_credentials(profile)
    if token:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token


def prompt_cache_point() -> dict[str, Any] | None:
    raw = os.environ.get("BEDROCK_PROMPT_CACHE_TTL", "1h").strip()
    if raw.lower() in {"", "0", "false", "off", "none"}:
        return None
    cache_point: dict[str, Any] = {"type": "default"}
    if raw:
        cache_point["ttl"] = raw
    return {"cachePoint": cache_point}


def messages_with_cache_point(
    messages: list[dict[str, Any]],
    cache_point: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if not cache_point or os.environ.get("BEDROCK_CACHE_CONVERSATION", "1").lower() in {
        "0",
        "false",
        "off",
        "none",
    }:
        return messages
    if not messages:
        return messages

    request_messages = [
        {"role": message["role"], "content": list(message.get("content", []))}
        for message in messages
    ]
    request_messages[-1]["content"].append(cache_point)
    return request_messages


def truncate(text: str, max_chars: int = 20000) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[truncated {len(text) - max_chars} chars]"


def append_transcript(section: str, content: str) -> None:
    TRANSCRIPT.parent.mkdir(parents=True, exist_ok=True)
    with TRANSCRIPT.open("a", encoding="utf-8") as fh:
        fh.write(f"\n\n## {section}\n\n{content.strip()}\n")


def run_command(argv: list[str], *, timeout: int = 600) -> tuple[int, str]:
    proc = subprocess.run(
        argv,
        cwd=str(WORKSPACE),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = proc.stdout
    if proc.stderr:
        output += "\n[stderr]\n" + proc.stderr
    return proc.returncode, truncate(output or "(no output)")


def tool_config() -> dict[str, Any]:
    string = {"type": "string"}
    integer = {"type": "integer"}
    string_array = {"type": "array", "items": string}
    return {
        "tools": [
            {
                "toolSpec": {
                    "name": "request_data",
                    "description": (
                        "Ask the guarded data-agent to grant specific measurements or datasets into "
                        "/workspace/data. Do not ask what data exists; name the measurement, organism, "
                        "condition, modality, or scope you need."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "question": string,
                                "modalities": {"type": "array", "items": string},
                                "max_bytes": integer,
                            },
                            "required": ["question"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "read_file",
                    "description": "Read a file under /workspace.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "path": string,
                                "line_start": integer,
                                "line_end": integer,
                                "max_chars": integer,
                            },
                            "required": ["path"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "search",
                    "description": "Regex search files under /workspace.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "pattern": string,
                                "file_glob": string,
                                "max_matches": integer,
                            },
                            "required": ["pattern"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "web_search",
                    "description": "Search the web with benchmark leakage guards and academic-search fallback.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "query": string,
                                "limit": integer,
                                "allowed_domains": string_array,
                                "blocked_domains": string_array,
                            },
                            "required": ["query"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "research_papers",
                    "description": (
                        "Search literature metadata or passages for background methods and related "
                        "datasets. Uses Semantic Scholar with retries/fallbacks; direct target-paper "
                        "retrieval is blocked."
                    ),
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {
                                "operation": {"type": "string", "enum": ["search", "snippet_search"]},
                                "query": string,
                                "limit": integer,
                            },
                            "required": ["operation", "query"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "fetch_webpage",
                    "description": "Fetch an allowed webpage into /workspace/reference.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"url": string, "max_chars": integer},
                            "required": ["url"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "run_command",
                    "description": "Run a constrained read-only command in /workspace.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"command": string, "timeout": integer},
                            "required": ["command"],
                        }
                    },
                }
            },
            {
                "toolSpec": {
                    "name": "check_space",
                    "description": "Check sandbox disk usage against the configured budget.",
                    "inputSchema": {"json": {"type": "object", "properties": {}}},
                }
            },
            {
                "toolSpec": {
                    "name": "submit_answer",
                    "description": "Submit the final answer and end the run.",
                    "inputSchema": {
                        "json": {
                            "type": "object",
                            "properties": {"answer": string},
                            "required": ["answer"],
                        }
                    },
                }
            },
        ]
    }


def execute_tool(name: str, payload: dict[str, Any]) -> tuple[bool, str, bool]:
    submitted = False
    if name == "request_data":
        argv = ["request_data", str(payload["question"])]
        for modality in payload.get("modalities") or []:
            argv.extend(["--modality", str(modality)])
        if payload.get("max_bytes"):
            argv.extend(["--max-bytes", str(payload["max_bytes"])])
    elif name == "read_file":
        argv = ["read_file", str(payload["path"])]
        if payload.get("line_start"):
            argv.extend(["--line-start", str(payload["line_start"])])
        if payload.get("line_end"):
            argv.extend(["--line-end", str(payload["line_end"])])
        if payload.get("max_chars"):
            argv.extend(["--max-chars", str(payload["max_chars"])])
    elif name == "search":
        argv = ["search", str(payload["pattern"])]
        if payload.get("file_glob"):
            argv.extend(["--file-glob", str(payload["file_glob"])])
        if payload.get("max_matches"):
            argv.extend(["--max-matches", str(payload["max_matches"])])
    elif name == "web_search":
        argv = ["web_search", str(payload["query"])]
        for domain in payload.get("allowed_domains") or []:
            argv.extend(["--allowed-domain", str(domain)])
        for domain in payload.get("blocked_domains") or []:
            argv.extend(["--blocked-domain", str(domain)])
        if payload.get("limit"):
            argv.extend(["--limit", str(payload["limit"])])
    elif name == "research_papers":
        argv = ["research_papers", str(payload["operation"]), "--query", str(payload["query"])]
        if payload.get("limit"):
            argv.extend(["--limit", str(payload["limit"])])
    elif name == "fetch_webpage":
        argv = ["fetch_webpage", str(payload["url"])]
        if payload.get("max_chars"):
            argv.extend(["--max-chars", str(payload["max_chars"])])
    elif name == "run_command":
        argv = ["run_command", str(payload["command"])]
        if payload.get("timeout"):
            argv.extend(["--timeout", str(payload["timeout"])])
    elif name == "check_space":
        argv = ["check_space"]
    elif name == "submit_answer":
        answer = str(payload["answer"])
        FINAL_ANSWER.write_text(answer, encoding="utf-8")
        append_transcript("Final Answer", answer)
        argv = ["submit_answer", "--file", str(FINAL_ANSWER), "--transcript", str(TRANSCRIPT)]
        submitted = True
    else:
        return False, f"Unknown tool: {name}", False

    code, output = run_command(argv)
    rendered = f"$ {shlex.join(argv)}\n[exit code: {code}]\n\n{output}"
    append_transcript(f"Tool: {name}", rendered)
    return code == 0, rendered, submitted


def build_system_message(task: str) -> str:
    return f"""You are the agent-under-evaluation in a blinded biology discovery benchmark.

You are inside /workspace. You do not have the original paper, repository, answer key,
or hidden benchmark files. Use the provided tools to search background literature, ask
the guarded data-agent for datasets, inspect granted data, run analyses, and produce
scientific conclusions.

Do not ask for the original paper, DOI, author code, repository, solution, answer key,
or expected conclusions. Ask for measurements or datasets instead.

Data requests must be specific. The data-agent may deny broad inventory-style requests
such as "do you have any datasets?" or "give me all available data." Ask for concrete
data by measurement, organism/sample, condition, modality, cohort, rows/columns, or file
type, and make follow-up requests when you need additional data.

Installed environment:
- Python 3.11 with boto3, biopython, jupyter, lifelines, matplotlib, numpy, openpyxl,
  pandas, pyarrow, requests, scikit-learn, scipy, and statsmodels.
- Rscript from R base is available for reading .rds files and running compact R one-liners.
- Common read-only CLI tools include ls, find, rg, grep, awk, sed, sort, uniq, wc, head,
  tail, cut, paste, join, diff, comm, file, xxd, jq, tar, unzip, zipinfo, env, pwd, and df.
- run_command executes commands directly without a shell. Shell pipelines, redirects,
  command substitution, package installation, network transfer commands, and destructive
  filesystem commands are blocked. Prefer short Python/R one-liners or read_file/search
  for data inspection.

Use tools as needed. When finished, call submit_answer with a concise but complete final
answer including evidence, caveats, and uncertainty.

Task:
{task}
"""


def extract_text_and_tools(content: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    text_parts = []
    tools = []
    for item in content:
        if "text" in item:
            text_parts.append(item["text"])
        if "toolUse" in item:
            tools.append(item["toolUse"])
    return "\n".join(text_parts).strip(), tools


def create_client(api_base: str):
    import boto3
    from botocore.config import Config as BotoConfig

    profile = os.environ.get("AWS_PROFILE")
    ensure_bedrock_bearer_token(profile)
    session_kwargs = {"profile_name": profile} if profile else {}
    session = boto3.Session(**session_kwargs)
    region = (
        region_from_api_base(api_base)
        or os.environ.get("BEDROCK_AWS_REGION")
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )
    return session.client(
        "bedrock-runtime",
        region_name=region,
        config=BotoConfig(
            connect_timeout=int(os.environ.get("BEDROCK_CONNECT_TIMEOUT", "10")),
            read_timeout=int(os.environ.get("BEDROCK_READ_TIMEOUT", "1800")),
            retries={"mode": "standard", "total_max_attempts": 1},
        ),
    )


def run_agent(args: argparse.Namespace) -> int:
    task = Path(args.task_file).read_text(encoding="utf-8")
    TRANSCRIPT.write_text(f"# UEA Bedrock Transcript\n\nStarted: {utc_now()}\n\n", encoding="utf-8")
    append_transcript("Task", task)

    client = create_client(args.api_base)
    system_blocks: list[dict[str, Any]] = [{"text": build_system_message(task)}]
    cache_point = prompt_cache_point()
    if cache_point:
        system_blocks.append(cache_point)

    messages: list[dict[str, Any]] = [
        {
            "role": "user",
            "content": [
                {
                    "text": (
                        "Begin the benchmark task. Check available space, request data as needed, "
                        "analyze the evidence, and submit the final answer when ready."
                    )
                }
            ],
        }
    ]
    submitted = False
    trace: list[dict[str, Any]] = []
    cost_tracker = BedrockCostTracker(component="uea", model=args.model)

    for step in range(1, args.max_steps + 1):
        current_tool_config = tool_config()
        if cache_point:
            current_tool_config["tools"].append(cache_point)
        response = client.converse(
            modelId=args.model.removeprefix("bedrock/"),
            system=system_blocks,
            messages=messages_with_cache_point(messages, cache_point),
            toolConfig=current_tool_config,
            inferenceConfig={
                "maxTokens": args.max_tokens,
                "temperature": args.temperature,
            },
        )
        usage = response.get("usage", {}) or {}
        call_cost = cost_tracker.record(usage)
        assistant_message = response.get("output", {}).get("message", {})
        content = assistant_message.get("content", [])
        text, tool_uses = extract_text_and_tools(content)
        messages.append({"role": "assistant", "content": content})
        trace.append(
            {
                "step": step,
                "assistant": content,
                "usage": usage,
                "cost_usd": round(call_cost, 6),
            }
        )
        if text:
            append_transcript(f"Assistant Step {step}", text)

        if not tool_uses:
            final = text or "No final answer was produced."
            FINAL_ANSWER.write_text(final, encoding="utf-8")
            append_transcript("Final Answer", final)
            ok, output, _ = execute_tool("submit_answer", {"answer": final})
            submitted = ok
            print(output)
            break

        tool_results = []
        for tool_use in tool_uses:
            name = tool_use["name"]
            payload = tool_use.get("input") or {}
            ok, output, did_submit = execute_tool(name, payload)
            print(output)
            tool_results.append(
                {
                    "toolResult": {
                        "toolUseId": tool_use["toolUseId"],
                        "status": "success" if ok else "error",
                        "content": [{"text": output}],
                    }
                }
            )
            submitted = submitted or did_submit
        messages.append({"role": "user", "content": tool_results})
        if submitted:
            break
    else:
        final = "Stopped after reaching the maximum number of agent steps without a final answer."
        ok, output, _ = execute_tool("submit_answer", {"answer": final})
        submitted = ok
        print(output)

    cost_tracker.finalize()
    TRACE.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if submitted else 1


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the BioEval UEA with AWS Bedrock Claude Sonnet 4.6.")
    parser.add_argument("--task-file", default="/workspace/TASK.md")
    parser.add_argument("--model", default=os.getenv("UEA_BEDROCK_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-base", default=os.getenv("UEA_BEDROCK_API_BASE", DEFAULT_API_BASE))
    parser.add_argument("--max-steps", type=int, default=int(os.getenv("UEA_MAX_STEPS", "40")))
    parser.add_argument("--max-tokens", type=int, default=int(os.getenv("UEA_MAX_TOKENS", "8192")))
    parser.add_argument("--temperature", type=float, default=float(os.getenv("UEA_TEMPERATURE", "0.2")))
    return parser


def main() -> int:
    try:
        return run_agent(build_arg_parser().parse_args())
    except Exception as exc:
        print(f"UEA Bedrock agent failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
