"""Catalog-driven staging of granted data.

Grants are assembled from the hidden per-problem catalog only. Files are first
collected into a private temp directory (never visible to the UEA), passed through
the leak guard, and only the survivors are copied into the mounted grant directory.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from bioeval import providers
from bioeval.catalog import resolve_entry_files
from bioeval.guard import enforce
from bioeval.schemas import CatalogEntry, DataCatalog, DatasetGrant, DatasetRequest, GrantedFile

# Requests for the paper/code/solution itself are refused outright.
DENIED_RE = re.compile(
    r"\b(paper|manuscript|article|authors'? code|source code|github|repository|"
    r"\brepo\b|solution|answer key|ground truth|expected (?:result|conclusion)|doi)\b",
    re.IGNORECASE,
)


@dataclass
class StageInstruction:
    entry_id: str
    rows: int | None = None
    columns: list[str] | None = None
    use_online: bool = False


@dataclass
class GrantPlan:
    instructions: list[StageInstruction] = field(default_factory=list)
    message: str = ""
    deny: bool = False
    deny_reason: str | None = None


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", text.lower())}


def select_instructions_by_keywords(catalog: DataCatalog, request: DatasetRequest) -> list[StageInstruction]:
    """Deterministic fallback selection when no LLM/opencode planner is available."""
    req_tokens = _tokens(" ".join([request.question, *request.desired_modalities]))
    scored: list[tuple[int, CatalogEntry]] = []
    for entry in catalog.grantable():
        hay = _tokens(" ".join([entry.id, entry.description, *entry.modalities]))
        score = len(req_tokens & hay)
        scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)

    # The deterministic fallback prefers local data and never triggers a surprise
    # network fetch; online entries are a deliberate LLM/agent choice.
    local = [(s, e) for s, e in scored if e.source_paths]
    top = [e for s, e in local if s > 0][:5]
    if not top:
        top = [e for _, e in local][:2]
    if not top:
        # No local data at all (e.g. a pure modeling problem): surface the catalog's
        # online/literature guidance entries without auto-downloading.
        top = [e for _, e in scored if e.online is None][:2]
        return [StageInstruction(entry_id=e.id, use_online=False) for e in top]
    return [StageInstruction(entry_id=e.id) for e in top]


def _derive_table(src: Path, dest: Path, rows: int | None, columns: list[str] | None) -> bool:
    """Write a row/column subset of a CSV/TSV/parquet. Returns True on success."""
    try:
        import pandas as pd  # noqa: PLC0415
    except Exception:
        return False
    suffix = src.suffix.lower()
    try:
        if suffix in {".csv", ".tsv", ".txt"}:
            sep = "\t" if suffix == ".tsv" else ","
            df = pd.read_csv(src, sep=sep, nrows=rows, usecols=columns)
            dest = dest.with_suffix(".csv")
            df.to_csv(dest, index=False)
        elif suffix == ".parquet":
            df = pd.read_parquet(src, columns=columns)
            if rows:
                df = df.head(rows)
            df.to_parquet(dest)
        else:
            return False
    except Exception:
        return False
    return True


def _stage_local_entry(
    entry: CatalogEntry,
    problem_root: Path,
    stage_dir: Path,
    instr: StageInstruction,
    *,
    remaining_bytes: int,
    notes: list[str],
) -> int:
    staged = 0
    for src in resolve_entry_files(problem_root, entry):
        rel = src.relative_to(problem_root / "data")
        dest = stage_dir / entry.id / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = src.stat().st_size
        wants_subset = instr.rows is not None or instr.columns is not None
        if wants_subset and _derive_table(src, dest, instr.rows, instr.columns):
            staged += dest.stat().st_size if dest.exists() else 0
            notes.append(f"Derived a subset of '{entry.id}/{rel.name}'.")
            continue
        if size > remaining_bytes - staged:
            notes.append(
                f"Skipped '{entry.id}/{rel.name}' ({size} bytes) to stay within the "
                f"{remaining_bytes} byte budget; ask for a subset (rows/columns)."
            )
            continue
        shutil.copy2(src, dest)
        staged += size
    return staged


def _stage_online_entry(
    entry: CatalogEntry,
    stage_dir: Path,
    *,
    per_file_bytes: int,
    remaining_bytes: int,
    notes: list[str],
) -> int:
    if not entry.online:
        notes.append(
            f"No direct download is configured for '{entry.id}'. {entry.description.strip()}"
        )
        return 0
    dest = stage_dir / entry.id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        fetched = providers.fetch_online_spec(
            entry.online,
            dest,
            max_bytes=per_file_bytes,
            max_total_bytes=remaining_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - report fetch failures, do not crash
        notes.append(f"Online fetch for '{entry.id}' failed: {exc}")
        return 0
    return sum(f.bytes for f in fetched)


def stage_and_grant(
    *,
    problem_root: Path,
    catalog: DataCatalog,
    identifiers: list[str],
    staging_root: Path,
    sandbox_data_root: str,
    request: DatasetRequest,
    request_id: str,
    plan: GrantPlan,
) -> DatasetGrant:
    if plan.deny or DENIED_RE.search(request.question):
        reason = plan.deny_reason or (
            "Denied: this asks for the paper, code, or solution. Request experimental "
            "measurements, public source data, or a derived dataset instead."
        )
        return DatasetGrant(request_id=request_id, status="denied", message=reason)

    notes: list[str] = []
    tmp_root = Path(tempfile.mkdtemp(prefix=f"bioeval_stage_{request_id}_"))
    try:
        remaining = request.max_bytes
        for instr in plan.instructions:
            entry = catalog.by_id(instr.entry_id)
            if entry is None:
                notes.append(f"Unknown dataset id '{instr.entry_id}'.")
                continue
            if not entry.grantable:
                notes.append(f"'{instr.entry_id}' is not grantable.")
                continue
            if remaining <= 0:
                notes.append("Reached the byte budget; request a subset for more.")
                break
            if instr.use_online or not entry.source_paths:
                used = _stage_online_entry(
                    entry,
                    tmp_root,
                    per_file_bytes=request.max_bytes,
                    remaining_bytes=remaining,
                    notes=notes,
                )
            else:
                used = _stage_local_entry(
                    entry,
                    problem_root,
                    tmp_root,
                    instr,
                    remaining_bytes=remaining,
                    notes=notes,
                )
            remaining -= used

        report = enforce(tmp_root, identifiers)

        grant_dir = staging_root / request_id
        grant_dir.mkdir(parents=True, exist_ok=True)
        granted_files: list[GrantedFile] = []
        for src in report.kept:
            rel = src.relative_to(tmp_root)
            dest = grant_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            granted_files.append(
                GrantedFile(
                    source_path=str(rel),
                    sandbox_path=f"{sandbox_data_root.rstrip('/')}/{request_id}/{rel}",
                    bytes=dest.stat().st_size,
                    reason="Matched the request and cleared the leak guard.",
                )
            )

        rejected_notes = [f"{rel}: {reason}" for rel, reason in report.rejected]
        if rejected_notes:
            notes.append(
                f"Withheld {len(rejected_notes)} item(s) that resembled code, models, "
                "documents, or paper identifiers."
            )

        status = "granted" if granted_files else "denied"
        if granted_files and (notes or rejected_notes):
            status = "partial"

        message = "; ".join(notes) if notes else (
            "Placed the requested public/source data into the sandbox data directory."
            if granted_files
            else "No grantable data matched this request. Try describing the measurement "
            "or public dataset you need."
        )

        grant = DatasetGrant(
            request_id=request_id,
            status=status,
            message=message,
            files=granted_files,
            rejected=rejected_notes,
            manifest_path=(
                f"{sandbox_data_root.rstrip('/')}/{request_id}/DATA_GRANT_MANIFEST.json"
                if granted_files
                else None
            ),
        )
        if granted_files:
            (grant_dir / "DATA_GRANT_MANIFEST.json").write_text(
                json.dumps(grant.model_dump(), indent=2)
            )
        return grant
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
