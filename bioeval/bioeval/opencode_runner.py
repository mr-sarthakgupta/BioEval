"""Drive the data-agent's reasoning with opencode (GPT-5.5), with safe fallbacks.

The data-agent's *decision* of which datasets to grant is made by an LLM:
1. opencode running GPT-5.5 in a locked-down per-request workspace (preferred), or
2. a direct OpenAI Responses call with a structured-output schema, or
3. deterministic keyword matching over the catalog (no network/keys needed).

In every case the LLM only ever sees the neutral public catalog and the UEA's
request. It produces a *plan*; the host executes staging and the leak guard. The
agent never moves files itself, so it cannot be a back door around the guard.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from bioeval.curation import GrantPlan, StageInstruction
from bioeval.data_agent_prompt import (
    DATA_AGENT_SYSTEM_PROMPT,
    PLAN_JSON_SCHEMA,
    render_user_message,
)

PLAN_FILENAME = "plan.json"


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
    (ws / "REQUEST.txt").write_text(json.dumps(request, indent=2))
    (ws / "AGENTS.md").write_text(DATA_AGENT_SYSTEM_PROMPT)
    opencode_config = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {"edit": "deny", "bash": "allow", "webfetch": "allow"},
        "agent": {
            "dataagent": {
                "mode": "primary",
                "prompt": DATA_AGENT_SYSTEM_PROMPT,
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
        "Read CATALOG.json and REQUEST.txt in this directory. Decide which datasets to "
        "grant and call the stage_local / derive_subset / fetch_online / deny tools to "
        "record your plan. If you cannot call tools, write the JSON plan to ./plan.json."
    )
    cmd = [
        "opencode", "run",
        "--dir", str(ws),
        "--model", model,
        "--agent", "dataagent",
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
            timeout=int(os.getenv("DATA_AGENT_OPENCODE_TIMEOUT", "600")),
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
                {"role": "system", "content": DATA_AGENT_SYSTEM_PROMPT},
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
