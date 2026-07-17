"""Leak guard enforced at the staging boundary.

Every file the experiment-agent wants to expose to the UEA passes through `enforce()`
before it is copied into the mounted grant directory. The guard is the last line of
defense: even if the catalog, the agent prompt, or an online provider misbehaves, a
file that looks like author code, a trained model, a manuscript/PDF, or any text that
contains paper/repo identifiers is withheld.
"""

from __future__ import annotations

import re
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

# Extensions that should never reach the UEA: source code, notebooks, and serialized
# model artifacts (trained author models are the solution).
CODE_EXTENSIONS = {
    ".py", ".r", ".ipynb", ".c", ".cc", ".cpp", ".h", ".hpp", ".js", ".ts",
    ".sh", ".bash", ".pl", ".jl", ".m", ".java", ".go", ".rs", ".rb", ".f90",
    ".rmd", ".qmd",
}
MODEL_EXTENSIONS = {
    ".pkl", ".pickle", ".pt", ".pth", ".ckpt", ".joblib", ".onnx", ".pb",
    ".h5", ".hdf5", ".safetensors",
}
DOC_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".tex", ".xls"}
METADATA_EXTENSIONS = {
    ".md", ".markdown", ".html", ".htm", ".json", ".jsonl", ".bib", ".ris", ".enw",
}
RESULT_EXTENSIONS = {".graphml"}

# Archives we inspect member-by-member.
INSPECTABLE_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2")
# Archives we cannot inspect with the stdlib -> always reject.
OPAQUE_ARCHIVE_SUFFIXES = (".rar", ".7z")

REPO_HINT_NAMES = {
    "setup.py", "pyproject.toml", "requirements.txt", "environment.yml",
    "readme.md", "readme.txt", "readme", "license", "license.txt", ".gitignore",
    "dockerfile", "makefile",
}
BLOCKED_BASENAMES = {
    "metadata.json",
    "readme.md",
    "readme.txt",
    "readme",
}
RESULT_NAME_RE = re.compile(
    r"(source[-_]?data|geneimp|keycluster|steinertree|deg[_-]?list|"
    r"(?:^|[_-])results?(?:[_-]|\.)|pdx[_-]?results)",
    re.IGNORECASE,
)
RESULT_WORKSHEET_RE = re.compile(
    r"("
    r"\bfig(?:ure)?\.?\s*\d|"
    r"\bedf\s*\d|"
    r"\bextended\s*data\b|"
    r"\bsource\s*data\b"
    r")",
    re.IGNORECASE,
)

_SCAN_CHUNK_BYTES = 1024 * 1024
_MAX_EXPANDED_SCAN_BYTES = 2_000_000_000


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


def _archive_content_leak(path: Path, markers: list[bytes]) -> str | None:
    if not markers:
        return None
    try:
        if _has_suffix(path.name, (".zip",)):
            with zipfile.ZipFile(path) as archive:
                members = [item for item in archive.infolist() if not item.is_dir()]
                if sum(item.file_size for item in members) > _MAX_EXPANDED_SCAN_BYTES:
                    return "archive expands beyond the safe inspection limit"
                for item in members:
                    with archive.open(item) as stream:
                        if _stream_contains_marker(stream, markers):
                            return "archive content matches a hidden paper/repo identifier"
        else:
            with tarfile.open(path) as archive:
                members = [item for item in archive.getmembers() if item.isfile()]
                if sum(item.size for item in members) > _MAX_EXPANDED_SCAN_BYTES:
                    return "archive expands beyond the safe inspection limit"
                for item in members:
                    stream = archive.extractfile(item)
                    if stream is not None:
                        with stream:
                            if _stream_contains_marker(stream, markers):
                                return "archive content matches a hidden paper/repo identifier"
    except Exception:
        return "archive could not be fully scanned for identifiers"
    return None


def _stream_contains_marker(stream, markers: list[bytes]) -> bool:
    overlap = max((len(marker) for marker in markers), default=1) - 1
    carry = b""
    while True:
        chunk = stream.read(_SCAN_CHUNK_BYTES)
        if not chunk:
            return False
        blob = (carry + chunk).lower()
        if any(marker and marker in blob for marker in markers):
            return True
        carry = blob[-overlap:] if overlap else b""


def _content_leak(path: Path, markers: list[bytes]) -> str | None:
    if not markers:
        return None
    try:
        with path.open("rb") as fh:
            leaked = _stream_contains_marker(fh, markers)
    except Exception:  # noqa: BLE001 - unreadable; do not leak
        return "file could not be scanned for identifiers"
    if leaked:
        return "content matches a hidden paper/repo identifier"
    return None


def _xlsx_sheet_names(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as zf:
            raw = zf.read("xl/workbook.xml")
    except Exception:
        return []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    names: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "sheet":
            name = element.attrib.get("name")
            if name:
                names.append(name)
    return names


def _xlsx_structure_leak(path: Path) -> str | None:
    for sheet_name in _xlsx_sheet_names(path):
        if RESULT_WORKSHEET_RE.search(sheet_name):
            return "spreadsheet contains figure/statistic/result worksheet names"
    return None


def _xlsx_content_leak(path: Path, markers: list[bytes]) -> str | None:
    reason = _xlsx_structure_leak(path)
    if reason:
        return reason
    if not markers:
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            xml_names = [
                name for name in zf.namelist()
                if name.endswith(".xml") and not name.startswith("xl/media/")
            ]
            expanded_bytes = sum(zf.getinfo(name).file_size for name in xml_names)
            if expanded_bytes > _MAX_EXPANDED_SCAN_BYTES:
                return "spreadsheet expands beyond the safe inspection limit"
            for name in xml_names:
                with zf.open(name) as stream:
                    if _stream_contains_marker(stream, markers):
                        return "spreadsheet metadata/content matches a hidden paper/repo identifier"
    except Exception:
        return "spreadsheet could not be scanned for identifiers"
    return None


def _build_markers(identifiers: list[str]) -> list[bytes]:
    markers: list[bytes] = []
    for raw_ident in identifiers:
        original = (raw_ident or "").strip()
        ident = original.lower()
        # Only use reasonably specific identifiers to avoid false positives in
        # legitimate data. Short all-caps method/repo markers are still useful.
        if len(ident) >= 8 or (len(ident) >= 5 and original.isupper()):
            markers.append(ident.encode("utf-8", "ignore"))
    return list(dict.fromkeys(markers))


def scan_file(path: Path, identifiers: list[str]) -> str | None:
    """Return a rejection reason, or None if the file is safe to grant."""
    name = path.name.lower()
    suffix = path.suffix.lower()

    if name in BLOCKED_BASENAMES:
        return "metadata/readme files are not grantable"
    if RESULT_NAME_RE.search(name):
        return "precomputed result/source-data files are not grantable"
    if suffix in CODE_EXTENSIONS:
        return "source code is not grantable"
    if suffix in MODEL_EXTENSIONS:
        return "serialized model artifact is not grantable"
    if suffix in DOC_EXTENSIONS:
        return "manuscript/document formats are not grantable"
    if suffix in METADATA_EXTENSIONS:
        return "metadata/readme files are not grantable"
    if suffix in RESULT_EXTENSIONS:
        return "precomputed result/network files are not grantable"
    if _has_suffix(name, OPAQUE_ARCHIVE_SUFFIXES):
        return "archive format cannot be inspected; withheld"
    if _has_suffix(name, INSPECTABLE_ARCHIVE_SUFFIXES):
        reason = _archive_is_clean(path)
        if reason:
            return reason

    markers = _build_markers(identifiers)
    if _has_suffix(name, INSPECTABLE_ARCHIVE_SUFFIXES):
        reason = _archive_content_leak(path, markers)
        if reason:
            return reason
    # Filename check.
    low_name = name
    for ident in identifiers:
        ident = (ident or "").strip().lower()
        if len(ident) >= 6 and ident in low_name:
            return "filename matches a hidden paper/repo identifier"
    if suffix == ".xlsx":
        reason = _xlsx_content_leak(path, markers)
        if reason:
            return reason
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
