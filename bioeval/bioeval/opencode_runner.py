"""Drive the experiment-agent's dataset matching with safe fallbacks.

The experiment-agent's *decision* of which feasible experiment data to grant is made by an LLM:
1. AWS Bedrock Claude Sonnet 4.6 via the native Converse API (default), or
2. opencode in a locked-down per-request workspace for OpenAI-compatible models, or
3. a direct OpenAI Responses call with a structured-output schema, or
4. deterministic keyword matching over the catalog (no network/keys needed).

In every case the LLM only ever sees the neutral public catalog and the UEA's
request. It produces a *plan*; the host executes staging and the leak guard. The
agent never moves files itself, so it cannot be a back door around the guard.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import configparser
from pathlib import Path

from bioeval.curation import GrantPlan, StageInstruction
from bioeval.data_agent_prompt import (
    EXPERIMENT_AGENT_MATCHING_PROMPT,
    PLAN_JSON_SCHEMA,
    render_user_message,
)

PLAN_FILENAME = "plan.json"


def _region_from_api_base(api_base: str | None) -> str | None:
    if not api_base:
        return None
    if api_base.startswith("bedrock:"):
        return api_base.split(":", 1)[1] or None
    return None


def is_bedrock_api_base(api_base: str | None) -> bool:
    return bool(api_base and api_base.startswith("bedrock"))


def _bedrock_api_key_from_aws_credentials(
    profile: str | None = None,
    credentials_path: Path | None = None,
) -> str | None:
    """Return a Bedrock API key stored in aws_session_token, matching skydiscover."""
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


def _ensure_bedrock_bearer_token(profile: str | None = None) -> None:
    if os.environ.get("AWS_BEARER_TOKEN_BEDROCK"):
        return
    token = _bedrock_api_key_from_aws_credentials(profile)
    if token:
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = token


def _prompt_cache_point() -> dict | None:
    raw = os.environ.get("BEDROCK_PROMPT_CACHE_TTL", "1h").strip()
    if raw.lower() in {"", "0", "false", "off", "none"}:
        return None
    cache_point = {"type": "default"}
    if raw:
        cache_point["ttl"] = raw
    return {"cachePoint": cache_point}


def _plan_from_obj(obj: dict) -> GrantPlan:
    instructions = []
    for raw in obj.get("instructions") or []:
        cols = raw.get("columns")
        instructions.append(
            StageInstruction(
                entry_id=str(raw["entry_id"]),
                rows=raw.get("rows"),
                columns=list(cols) if cols else None,
                use_online=bool(raw.get("use_online", False)),
            )
        )
    return GrantPlan(
        instructions=instructions,
        message=str(obj.get("message", "")),
        deny=bool(obj.get("deny", False)),
        deny_reason=obj.get("deny_reason"),
    )


def _extract_json_object(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def build_workspace(ws: Path, catalog_public: list[dict], request: dict) -> None:
    ws.mkdir(parents=True, exist_ok=True)
    (ws / "CATALOG.json").write_text(json.dumps(catalog_public, indent=2))
    (ws / "EXPERIMENT.json").write_text(json.dumps(request, indent=2))
    (ws / "AGENTS.md").write_text(EXPERIMENT_AGENT_MATCHING_PROMPT)
    opencode_config = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {"edit": "deny", "bash": "allow", "webfetch": "allow"},
        "agent": {
            "experimentagent": {
                "mode": "primary",
                "prompt": EXPERIMENT_AGENT_MATCHING_PROMPT,
                "permission": {"edit": "deny", "bash": "allow", "webfetch": "allow"},
            }
        },
    }
    (ws / "opencode.json").write_text(json.dumps(opencode_config, indent=2))


def read_plan_file(ws: Path) -> dict | None:
    path = ws / PLAN_FILENAME
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
    return None


def plan_with_opencode(ws: Path, model: str) -> GrantPlan | None:
    """Run opencode headless in the workspace. Returns None if opencode is unavailable."""
    if not shutil.which("opencode"):
        return None
    prompt = (
        "Read CATALOG.json and EXPERIMENT.json in this directory. Decide which datasets could "
        "grant and call the stage_local / derive_subset / fetch_online / deny tools to "
        "record your plan. If you cannot call tools, write the JSON plan to ./plan.json."
    )
    cmd = [
        "opencode", "run",
        "--dir", str(ws),
        "--model", model,
        "--agent", "experimentagent",
        "--format", "json",
        "--dangerously-skip-permissions",
        prompt,
    ]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ws),
            capture_output=True,
            text=True,
            timeout=int(os.getenv("EXPERIMENT_AGENT_OPENCODE_TIMEOUT", "600")),
            env={**os.environ, "BIOEVAL_REQUEST_DIR": str(ws)},
        )
    except Exception:  # noqa: BLE001 - fall back to other planners
        return None

    plan_obj = read_plan_file(ws)
    if plan_obj is None:
        plan_obj = _extract_json_object(proc.stdout or "")
    if plan_obj is None:
        return None
    return _plan_from_obj(plan_obj)


def plan_with_openai(catalog_public: list[dict], request: dict, model: str) -> GrantPlan | None:
    """Direct OpenAI Responses call with structured output. Returns None on failure."""
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI  # noqa: PLC0415

        client = OpenAI()
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": EXPERIMENT_AGENT_MATCHING_PROMPT},
                {"role": "user", "content": render_user_message(catalog_public, request)},
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "grant_plan",
                    "schema": PLAN_JSON_SCHEMA,
                    "strict": True,
                }
            },
        )
        obj = _extract_json_object(response.output_text)
    except Exception:  # noqa: BLE001 - fall back to keyword matching
        return None
    if obj is None:
        return None
    return _plan_from_obj(obj)


def plan_with_bedrock(
    catalog_public: list[dict],
    request: dict,
    model: str,
    api_base: str | None = None,
) -> GrantPlan | None:
    """Direct AWS Bedrock Converse call, using the same credential style as skydiscover."""
    try:
        import boto3  # noqa: PLC0415
        from botocore.config import Config as BotoConfig  # noqa: PLC0415
    except ImportError:
        return None

    try:
        profile = os.environ.get("AWS_PROFILE")
        _ensure_bedrock_bearer_token(profile)
        session_kwargs = {"profile_name": profile} if profile else {}
        session = boto3.Session(**session_kwargs)
        region = (
            _region_from_api_base(api_base)
            or os.environ.get("BEDROCK_AWS_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        client = session.client(
            "bedrock-runtime",
            region_name=region,
            config=BotoConfig(
                connect_timeout=int(os.environ.get("BEDROCK_CONNECT_TIMEOUT", "10")),
                read_timeout=int(os.environ.get("BEDROCK_READ_TIMEOUT", "300")),
                retries={"mode": "standard", "total_max_attempts": 1},
            ),
        )
        system_blocks = [{"text": EXPERIMENT_AGENT_MATCHING_PROMPT}]
        cache_point = _prompt_cache_point()
        if cache_point:
            system_blocks.append(cache_point)
        response = client.converse(
            modelId=model.removeprefix("bedrock/"),
            system=system_blocks,
            messages=[
                {
                    "role": "user",
                    "content": [{"text": render_user_message(catalog_public, request)}],
                }
            ],
            inferenceConfig={
                "maxTokens": int(os.environ.get("EXPERIMENT_AGENT_MAX_TOKENS", "4096")),
                "temperature": float(os.environ.get("EXPERIMENT_AGENT_TEMPERATURE", "0")),
            },
            toolConfig={
                "tools": [
                    {
                        "toolSpec": {
                            "name": "record_grant_plan",
                            "description": "Record the exact dataset compatibility plan.",
                            "inputSchema": {"json": PLAN_JSON_SCHEMA},
                        }
                    }
                ],
                "toolChoice": {"tool": {"name": "record_grant_plan"}},
            },
        )
        from bioeval.bedrock_cost import record_bedrock_usage

        record_bedrock_usage(response.get("usage", {}) or {}, component="experiment-agent", model=model)
        content = response.get("output", {}).get("message", {}).get("content", [])
        obj = next(
            (
                item["toolUse"]["input"]
                for item in content
                if isinstance(item, dict)
                and item.get("toolUse", {}).get("name") == "record_grant_plan"
            ),
            None,
        )
        text = "\n".join(
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("text")
        )
        if obj is None:
            obj = _extract_json_object(text)
    except Exception:  # noqa: BLE001 - fall back to the next planner
        return None
    if obj is None:
        return None
    return _plan_from_obj(obj)
