"""CLI tools the opencode experiment-agent matcher calls to record a grant plan.

Each tool appends to `plan.json` in the request workspace (BIOEVAL_REQUEST_DIR or the
current directory). The host then validates the plan against the hidden catalog and
performs the actual staging + leak-guard pass. These tools never move data themselves.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

PLAN_FILENAME = "plan.json"


def _plan_path() -> Path:
    base = Path(os.getenv("BIOEVAL_REQUEST_DIR", "."))
    return base / PLAN_FILENAME


def _load() -> dict:
    path = _plan_path()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return {"deny": False, "deny_reason": None, "message": "", "instructions": []}


def _save(plan: dict) -> None:
    _plan_path().write_text(json.dumps(plan, indent=2))


def _add_instruction(entry_id: str, rows: int | None, columns: list[str] | None, use_online: bool) -> None:
    plan = _load()
    plan["instructions"].append(
        {"entry_id": entry_id, "rows": rows, "columns": columns or None, "use_online": use_online}
    )
    _save(plan)


def _columns(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [c.strip() for c in value.split(",") if c.strip()]


def stage_local() -> None:
    p = argparse.ArgumentParser(description="Grant a local dataset (optionally subset).")
    p.add_argument("--id", required=True)
    p.add_argument("--rows", type=int)
    p.add_argument("--columns")
    args = p.parse_args()
    _add_instruction(args.id, args.rows, _columns(args.columns), use_online=False)
    print(f"recorded stage_local for {args.id}")


def derive_subset() -> None:
    p = argparse.ArgumentParser(description="Grant a row/column subset of a local dataset.")
    p.add_argument("--id", required=True)
    p.add_argument("--rows", type=int, required=True)
    p.add_argument("--columns")
    args = p.parse_args()
    _add_instruction(args.id, args.rows, _columns(args.columns), use_online=False)
    print(f"recorded derive_subset for {args.id}")


def fetch_online() -> None:
    p = argparse.ArgumentParser(description="Download an online dataset.")
    p.add_argument("--id", required=True)
    args = p.parse_args()
    _add_instruction(args.id, None, None, use_online=True)
    print(f"recorded fetch_online for {args.id}")


def deny() -> None:
    p = argparse.ArgumentParser(description="Refuse the whole request.")
    p.add_argument("--reason", required=True)
    args = p.parse_args()
    plan = _load()
    plan["deny"] = True
    plan["deny_reason"] = args.reason
    _save(plan)
    print("recorded deny")
