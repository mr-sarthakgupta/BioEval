"""Hidden, host-only data catalogs.

Each problem folder carries a `data_catalog.yaml` that enumerates the datasets the
experiment-agent may grant (and the ones it must never grant, e.g. author code, trained
models, figure source data, supplementary-information PDFs). The catalog decouples
grant decisions from (leaky) filenames and gives the leak guard an explicit allowlist.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from bioeval.schemas import CatalogEntry, DataCatalog

CATALOG_FILENAME = "data_catalog.yaml"


def catalog_path_for(problem_root: Path) -> Path:
    return problem_root / CATALOG_FILENAME


def load_catalog(problem_root: Path) -> DataCatalog:
    path = catalog_path_for(problem_root)
    if not path.exists():
        raise FileNotFoundError(
            f"No data catalog found at {path}. Every problem needs a data_catalog.yaml."
        )
    raw = yaml.safe_load(path.read_text()) or {}
    catalog = DataCatalog.model_validate(raw)
    if catalog.problem_id != problem_root.name:
        raise ValueError(
            f"Catalog problem_id {catalog.problem_id!r} does not match "
            f"directory {problem_root.name!r}."
        )
    return catalog


def resolve_entry_files(problem_root: Path, entry: CatalogEntry) -> list[Path]:
    """Expand an entry's source globs without exposing host layout to the UEA."""
    source_root = problem_root / ("data" if entry.source_base == "data" else "")
    source_root = source_root.resolve()
    allowed_root = source_root
    if entry.grantable and entry.source_base == "problem":
        allowed_root = (problem_root / "curated").resolve()
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in entry.source_paths:
        for match in sorted(source_root.glob(pattern)):
            if not match.is_file():
                continue
            resolved = match.resolve()
            # Grantable problem-relative files are restricted to the neutral curated tree.
            try:
                resolved.relative_to(allowed_root)
            except ValueError:
                continue
            if resolved not in seen:
                seen.add(resolved)
                files.append(match)
    return files
