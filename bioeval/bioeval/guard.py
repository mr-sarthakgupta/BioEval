"""Leak guard enforced at the staging boundary.

Every file the data-agent wants to expose to the UEA passes through `enforce()`
before it is copied into the mounted grant directory. The guard is the last line of
defense: even if the catalog, the agent prompt, or an online provider misbehaves, a
file that looks like author code, a trained model, a manuscript/PDF, or any text that
contains paper/repo identifiers is withheld.
"""

from __future__ import annotations

import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Extensions that should never reach the UEA: source code, notebooks, and serialized
# model artifacts (trained author models are the solution).
CODE_EXTENSIONS = {
    ".py", ".r", ".ipynb", ".c", ".cc", ".cpp", ".h", ".hpp", ".js", ".ts",
    ".sh", ".bash", ".pl", ".jl", ".m", ".java", ".go", ".rs", ".rb", ".f90",
}
MODEL_EXTENSIONS = {
    ".pkl", ".pickle", ".pt", ".pth", ".ckpt", ".joblib", ".onnx", ".pb",
    ".h5", ".hdf5", ".safetensors",
}
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".tex"}

# Archives we inspect member-by-member.
INSPECTABLE_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")
# Archives we cannot inspect with the stdlib -> always reject.
OPAQUE_ARCHIVE_SUFFIXES = (".rar", ".7z")

REPO_HINT_NAMES = {
    "setup.py", "pyproject.toml", "requirements.txt", "environment.yml",
    "readme.md", "readme.txt", "readme", "license", "license.txt", ".gitignore",
    "dockerfile", "makefile",
}

_BYTE_SCAN_LIMIT = 6_000_000  # scan up to ~6 MB of head + tail per file


@dataclass
class GuardReport:
    kept: list[Path] = field(default_factory=list)
    rejected: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.rejected


def _has_suffix(name: str, suffixes: tuple[str, ...]) -> bool:
    low = name.lower()
    return any(low.endswith(s) for s in suffixes)


def _archive_is_clean(path: Path) -> str | None:
    """Return a rejection reason if the archive contains code/notebooks/repo files."""
    try:
        names: list[str] = []
        if _has_suffix(path.name, (".zip",)):
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
        else:
            with tarfile.open(path) as tf:
                names = tf.getnames()
    except Exception as exc:  # noqa: BLE001 - opaque/corrupt archive is unsafe
        return f"could not inspect archive ({exc}); withheld"

    for raw in names:
        base = Path(raw).name.lower()
        suffix = Path(base).suffix
        if suffix in CODE_EXTENSIONS or suffix in MODEL_EXTENSIONS or suffix in DOC_EXTENSIONS:
            return f"archive contains restricted file '{raw}'"
        if base in REPO_HINT_NAMES or ".git/" in raw.lower():
            return f"archive looks like a code repository ('{raw}')"
    return None


def _read_scan_bytes(path: Path) -> bytes:
    size = path.stat().st_size
    with path.open("rb") as fh:
        if size <= _BYTE_SCAN_LIMIT:
            return fh.read()
        head = fh.read(_BYTE_SCAN_LIMIT // 2)
        fh.seek(-_BYTE_SCAN_LIMIT // 2, 2)
        tail = fh.read()
    return head + tail


def _content_leak(path: Path, markers: list[bytes]) -> str | None:
    if not markers:
        return None
    try:
        blob = _read_scan_bytes(path).lower()
    except Exception:  # noqa: BLE001 - unreadable; do not leak
        return "file could not be scanned for identifiers"
    for marker in markers:
        if marker and marker in blob:
            return f"content matches a hidden paper/repo identifier"
    return None


def _build_markers(identifiers: list[str]) -> list[bytes]:
    markers: list[bytes] = []
    for ident in identifiers:
        ident = (ident or "").strip().lower()
        # Only use reasonably specific identifiers to avoid false positives in
        # legitimate data (e.g. a column named "longevity").
        if len(ident) >= 8:
            markers.append(ident.encode("utf-8", "ignore"))
    return list(dict.fromkeys(markers))


def scan_file(path: Path, identifiers: list[str]) -> str | None:
    """Return a rejection reason, or None if the file is safe to grant."""
    name = path.name.lower()
    suffix = path.suffix.lower()

    if suffix in CODE_EXTENSIONS:
        return "source code is not grantable"
    if suffix in MODEL_EXTENSIONS:
        return "serialized model artifact is not grantable"
    if suffix in DOC_EXTENSIONS:
        return "manuscript/document formats are not grantable"
    if _has_suffix(name, OPAQUE_ARCHIVE_SUFFIXES):
        return "archive format cannot be inspected; withheld"
    if _has_suffix(name, INSPECTABLE_ARCHIVE_SUFFIXES):
        reason = _archive_is_clean(path)
        if reason:
            return reason

    markers = _build_markers(identifiers)
    # Filename check.
    low_name = name
    for ident in identifiers:
        ident = (ident or "").strip().lower()
        if len(ident) >= 6 and ident in low_name:
            return "filename matches a hidden paper/repo identifier"
    return _content_leak(path, markers)


def enforce(stage_dir: Path, identifiers: list[str]) -> GuardReport:
    """Scan everything under `stage_dir`; reject (delete) unsafe files in place."""
    report = GuardReport()
    for path in sorted(stage_dir.rglob("*")):
        if not path.is_file():
            continue
        reason = scan_file(path, identifiers)
        if reason:
            rel = path.relative_to(stage_dir)
            report.rejected.append((rel, reason))
            try:
                path.unlink()
            except OSError:
                pass
        else:
            report.kept.append(path)
    return report
