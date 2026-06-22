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
INVENTORY_REQUEST_RE = re.compile(
    r"\b(do you have|what (?:data|datasets)|which (?:data|datasets)|any datasets?|"
    r"all (?:data|datasets)|everything|anything related|available (?:data|datasets)|"
    r"datasets? on)\b",
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


def is_inventory_request(question: str) -> bool:
    """Return True for broad catalog-discovery requests that should be clarified."""
    return bool(INVENTORY_REQUEST_RE.search(question))


def clarification_message() -> str:
    return (
        "Please make a specific data request: name the measurement/data type plus the "
        "organism/sample, condition/treatment, modality, cohort, or desired rows/columns. "
        "I cannot answer broad inventory requests or dump all related datasets."
    )


def select_instructions_by_keywords(catalog: DataCatalog, request: DatasetRequest) -> list[StageInstruction]:
    """Deterministic fallback selection when no LLM/opencode planner is available."""
    if is_inventory_request(request.question):
        return []
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


def _neutral_file_name(index: int, src: Path) -> str:
    suffix = src.suffix.lower()
    return f"file_{index:03d}{suffix or '.dat'}"


def _stage_local_entry(
    entry: CatalogEntry,
    problem_root: Path,
    stage_dir: Path,
    instr: StageInstruction,
    *,
    public_entry_id: str,
    remaining_bytes: int,
    notes: list[str],
) -> int:
    staged = 0
    for file_index, src in enumerate(resolve_entry_files(problem_root, entry), start=1):
        neutral_name = _neutral_file_name(file_index, src)
        dest = stage_dir / public_entry_id / neutral_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        size = src.stat().st_size
        wants_subset = instr.rows is not None or instr.columns is not None
        if wants_subset and _derive_table(src, dest, instr.rows, instr.columns):
            staged += dest.stat().st_size if dest.exists() else 0
            notes.append(f"Derived a requested table subset for '{public_entry_id}/{neutral_name}'.")
            continue
        if size > remaining_bytes - staged:
            notes.append(
                f"Skipped '{public_entry_id}/{neutral_name}' ({size} bytes) to stay within the "
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
    public_entry_id: str,
    per_file_bytes: int,
    remaining_bytes: int,
    notes: list[str],
) -> int:
    if not entry.online:
        notes.append(
            f"No direct download is configured for '{public_entry_id}'. {entry.description.strip()}"
        )
        return 0
    dest = stage_dir / public_entry_id
    dest.mkdir(parents=True, exist_ok=True)
    try:
        fetched = providers.fetch_online_spec(
            entry.online,
            dest,
            max_bytes=per_file_bytes,
            max_total_bytes=remaining_bytes,
        )
    except Exception as exc:  # noqa: BLE001 - report fetch failures, do not crash
        notes.append(f"Online fetch for '{public_entry_id}' failed: {exc}")
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
    if is_inventory_request(request.question):
        return DatasetGrant(
            request_id=request_id,
            status="denied",
            message=clarification_message(),
        )

    notes: list[str] = []
    tmp_root = Path(tempfile.mkdtemp(prefix=f"bioeval_stage_{request_id}_"))
    try:
        remaining = request.max_bytes
        for instr in plan.instructions:
            entry = catalog.by_id_or_public_id(instr.entry_id)
            if entry is None:
                notes.append(f"Unknown requested dataset id '{instr.entry_id}'.")
                continue
            public_entry_id = catalog.public_id_for(entry.id) or "dataset_unknown"
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
                    public_entry_id=public_entry_id,
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
                    public_entry_id=public_entry_id,
                    remaining_bytes=remaining,
                    notes=notes,
                )
            remaining -= used

        report = enforce(tmp_root, identifiers)

        grant_dir = staging_root / request_id
        grant_dir.mkdir(parents=True, exist_ok=True)
        granted_files: list[GrantedFile] = []
        final_counts: dict[str, int] = {}
        for src in report.kept:
            staged_rel = src.relative_to(tmp_root)
            dataset_dir = (
                staged_rel.parts[0]
                if staged_rel.parts and re.fullmatch(r"dataset_\d{3}", staged_rel.parts[0])
                else "dataset_000"
            )
            final_counts[dataset_dir] = final_counts.get(dataset_dir, 0) + 1
            rel = Path(dataset_dir) / _neutral_file_name(final_counts[dataset_dir], src)
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
