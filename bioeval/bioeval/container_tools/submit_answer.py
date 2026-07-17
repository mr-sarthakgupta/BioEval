#!/usr/bin/env python3
"""Submit the UEA's final answer from inside the sandbox.

Writes the final answer and analysis transcript to the host-mounted submit directory,
where `bioeval-judge` can score it. This is how the UEA ends a run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def append_tool_event(record: dict) -> None:
    path = Path(os.getenv("BIOEVAL_TOOL_LOG", "/submit/tool_calls.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit your final answer for judging.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--text", help="Final answer text.")
    src.add_argument("--file", type=Path, help="Path to a file containing the final answer.")
    parser.add_argument("--transcript", type=Path, required=True, help="Analysis log to include.")
    parser.add_argument(
        "--analysis-manifest",
        type=Path,
        help=(
            "Optional JSON manifest with an artifacts array. Artifact paths are relative "
            "to the manifest and are copied into the submission."
        ),
    )
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

    if not args.transcript.exists():
        print(f"Transcript does not exist: {args.transcript}", file=sys.stderr)
        return 1
    submitted_artifacts = 0
    if args.analysis_manifest is not None:
        try:
            workspace_root = Path(
                os.getenv("BIOEVAL_WORKSPACE_ROOT", "/workspace")
            ).resolve()
            manifest_path = args.analysis_manifest.resolve()
            manifest = json.loads(manifest_path.read_text(errors="replace"))
            artifacts = manifest.get("artifacts")
            if not isinstance(artifacts, list) or not artifacts:
                raise ValueError("manifest must contain a non-empty artifacts array")
            copied = []
            artifact_dir = submit_dir / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(artifacts, start=1):
                if not isinstance(item, dict) or not item.get("path"):
                    raise ValueError("each artifact must be an object with a path")
                source = (manifest_path.parent / str(item["path"])).resolve()
                source.relative_to(workspace_root)
                if not source.is_file():
                    raise ValueError(f"artifact does not exist: {item['path']}")
                destination = artifact_dir / f"artifact_{index:03d}{source.suffix.lower()}"
                shutil.copy2(source, destination)
                copied_item = dict(item)
                copied_item["path"] = str(destination.relative_to(submit_dir))
                copied_item["sha256"] = hashlib.sha256(destination.read_bytes()).hexdigest()
                copied.append(copied_item)
            manifest["artifacts"] = copied
            (submit_dir / "analysis_manifest.json").write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False)
            )
            submitted_artifacts = len(copied)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Invalid analysis manifest: {exc}", file=sys.stderr)
            return 1

    answer = args.text if args.text is not None else args.file.read_text(errors="replace")
    (submit_dir / "final_answer.txt").write_text(answer)
    (submit_dir / "transcript.txt").write_text(args.transcript.read_text(errors="replace"))
    append_tool_event(
        {
            "event": "tool_call",
            "tool": "submit_answer",
            "timestamp": utc_now(),
            "run_id": os.getenv("BIOEVAL_RUN_ID"),
            "status": "ok",
            "answer_bytes": len(answer.encode("utf-8", "replace")),
            "transcript_path": str(args.transcript),
            "transcript_bytes": args.transcript.stat().st_size,
            "analysis_manifest_path": (
                str(args.analysis_manifest) if args.analysis_manifest else None
            ),
            "submitted_artifacts": submitted_artifacts,
        }
    )

    print(f"Submitted final answer to {submit_dir / 'final_answer.txt'}.")
    print("The benchmark operator can now run bioeval-judge on this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
