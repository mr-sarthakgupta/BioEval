#!/usr/bin/env python3
"""Download additional datasets into paper-invert problems."""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path("/home/mrsar/paper-invert")
PROBLEMS = ROOT / "problems"
PAPERS = ROOT / "papers"
UA = "paper-invert/1.0"


def fmt_bytes(n: int | float) -> str:
    n = float(n)
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024:.1f} KB"


def download_file(url: str, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return dest.stat().st_size
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=600) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return len(data)


def download_zenodo(record_id: str, dest_dir: Path) -> list[dict]:
    meta = json.loads(
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://zenodo.org/api/records/{record_id}",
                headers={"User-Agent": UA},
            ),
            timeout=120,
        ).read()
    )
    target = dest_dir / record_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    entries = []
    for f in meta.get("files", []):
        path = target / f["key"]
        size = download_file(f["links"]["self"], path)
        entries.append(
            {
                "source": "zenodo",
                "record_id": record_id,
                "file": str(path.relative_to(dest_dir.parent.parent)),
                "bytes": size,
            }
        )
    return entries


def download_urls(urls: list[tuple[str, Path]], source: str = "nature-supplementary") -> list[dict]:
    entries = []
    for url, dest in urls:
        try:
            size = download_file(url, dest)
            entries.append(
                {
                    "source": source,
                    "file": str(dest.relative_to(dest.parent.parent.parent)),
                    "bytes": size,
                    "url": url,
                }
            )
            print(f"  OK {dest.name}: {fmt_bytes(size)}")
        except Exception as exc:  # noqa: BLE001
            entries.append(
                {
                    "source": source,
                    "file": str(dest.name),
                    "bytes": 0,
                    "url": url,
                    "error": str(exc),
                }
            )
            print(f"  FAIL {dest.name}: {exc}")
    return entries


def merge_manifest(problem_dir: Path, new_entries: list[dict]) -> None:
    manifest_path = problem_dir / "data" / "MANIFEST.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing_keys = {
            (e.get("source"), e.get("file"), e.get("url"), e.get("record_id"))
            for e in manifest.get("entries", [])
        }
        for entry in new_entries:
            key = (entry.get("source"), entry.get("file"), entry.get("url"), entry.get("record_id"))
            if key not in existing_keys:
                manifest.setdefault("entries", []).append(entry)
    else:
        manifest = {
            "problem_id": problem_dir.name,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "entries": new_entries,
        }
    manifest["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    manifest["total_bytes"] = sum(
        e.get("bytes", 0) for e in manifest["entries"] if isinstance(e.get("bytes"), int)
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def setup_problem_dir(problem_id: str, pdf_name: str, readme_lines: list[str]) -> Path:
    problem_dir = PROBLEMS / problem_id
    (problem_dir / "paper").mkdir(parents=True, exist_ok=True)
    (problem_dir / "data").mkdir(parents=True, exist_ok=True)
    src = PAPERS / pdf_name
    dst = problem_dir / "paper" / pdf_name
    if src.exists():
        shutil.copy2(src, dst)
    readme = [f"# {problem_id}", ""] + readme_lines + [""]
    (problem_dir / "README.md").write_text("\n".join(readme), encoding="utf-8")
    return problem_dir


def download_soil_supplementary() -> None:
    print("\n=== Soil supplementary ===")
    problem_dir = PROBLEMS / "s41467-026-71453-5_soil-metagenome-fticr-integration"
    urls = [
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-71453-5/MediaObjects/41467_2026_71453_MOESM1_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-71453-5/MediaObjects/41467_2026_71453_MOESM2_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-71453-5/MediaObjects/41467_2026_71453_MOESM3_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-71453-5/MediaObjects/41467_2026_71453_MOESM4_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-71453-5/MediaObjects/41467_2026_71453_MOESM5_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-71453-5/MediaObjects/41467_2026_71453_MOESM6_ESM.xlsx",
    ]
    targets = [
        (u, problem_dir / "data" / "nature-supplementary" / unquote(u.split("/")[-1]))
        for u in urls
    ]
    entries = download_urls(targets)
    merge_manifest(problem_dir, entries)


def download_s41586() -> None:
    print("\n=== s41586 mitochondria-NPC ===")
    problem_id = "s41586-026-10588-3_mitochondria-nuclear-pore-interaction"
    problem_dir = setup_problem_dir(
        problem_id,
        "s41586-026-10588-3.pdf",
        [
            "**Title:** Mitochondria directly interact with the nuclear pore complex",
            "**DOI:** [10.1038/s41586-026-10588-3](https://doi.org/10.1038/s41586-026-10588-3)",
            "",
            "## Repositories",
            "- `repo/phylogeny` → https://github.com/akwestfall/EvolutionRANBP2",
            "- Biophysics Colab: https://colab.research.google.com/drive/10ufpBhsLk96DidzzFEsj79KGXr2iGR64",
            "",
            "## Raw data (not bulk-downloaded)",
            "- GEO: GSE325290, GSE324951, GSE324952",
            "- PRIDE: PXD065792, PXD065793",
        ],
    )

    urls = [
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM1_ESM.docx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM2_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM3_ESM.docx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM4_ESM.zip",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM5_ESM.docx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM6_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM7_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM8_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM9_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM10_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-026-10588-3/MediaObjects/41586_2026_10588_MOESM11_ESM.xlsx",
    ]
    targets = [
        (u, problem_dir / "data" / "nature-supplementary" / unquote(u.split("/")[-1]))
        for u in urls
    ]
    entries = download_urls(targets)

    geo_dir = problem_dir / "data" / "metadata" / "geo"
    geo_dir.mkdir(parents=True, exist_ok=True)
    for gse in ["GSE325290", "GSE324951", "GSE324952"]:
        url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}&targ=self&form=text&view=brief"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
        path = geo_dir / f"{gse}.soft"
        path.write_text(text, encoding="utf-8")
        entries.append(
            {
                "source": "geo",
                "accession": gse,
                "file": str(path.relative_to(problem_dir)),
                "bytes": path.stat().st_size,
            }
        )
        print(f"  OK {gse}.soft")

    ext = problem_dir / "data" / "external"
    for name, note in [
        ("pride", "PXD065792, PXD065793 — raw proteomics on PRIDE FTP (multi-GB)."),
        ("geo-sra", "RNA-seq/ChIP/ATAC raw reads on SRA via GEO accessions above."),
    ]:
        d = ext / name
        d.mkdir(parents=True, exist_ok=True)
        readme = d / "README.md"
        readme.write_text(note + "\n", encoding="utf-8")
        entries.append({"source": name, "file": str(readme.relative_to(problem_dir)), "bytes": readme.stat().st_size, "downloaded": False})

    write_manifest(problem_dir, entries)


def download_s41589() -> None:
    print("\n=== s41589 IDR condensate miscibility ===")
    problem_id = "s41589-026-02251-9_idr-condensate-serine-charge"
    problem_dir = setup_problem_dir(
        problem_id,
        "s41589-026-02251-9.pdf",
        [
            "**Title:** Opposing roles of serine and charge in IDR condensate miscibility",
            "**DOI:** [10.1038/s41589-026-02251-9](https://doi.org/10.1038/s41589-026-02251-9)",
            "",
            "## Repository",
            "- `repo/` → https://github.com/GFP12345/Opposing_Roles_of_Serine_and_Charge_in_IDR_Condensate_Miscibility",
        ],
    )

    entries = download_zenodo("19565235", problem_dir / "data" / "zenodo")
    for e in entries:
        print(f"  OK zenodo/{e['file'].split('/')[-1]}: {fmt_bytes(e['bytes'])}")

    urls = [
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM1_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM2_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM3_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM4_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM5_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM6_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM7_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM8_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM9_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM10_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM11_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM12_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM13_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM14_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM15_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM16_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM17_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM18_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM19_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM20_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM21_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM22_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM23_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM24_ESM.xlsx",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM25_ESM.pdf",
        "https://static-content.springer.com/esm/art%3A10.1038%2Fs41589-026-02251-9/MediaObjects/41589_2026_2251_MOESM26_ESM.xlsx",
    ]
    targets = [
        (u, problem_dir / "data" / "nature-supplementary" / unquote(u.split("/")[-1]))
        for u in urls
    ]
    entries.extend(download_urls(targets))
    write_manifest(problem_dir, entries)


def write_manifest(problem_dir: Path, entries: list[dict]) -> None:
    manifest = {
        "problem_id": problem_dir.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entries": entries,
        "total_bytes": sum(e.get("bytes", 0) for e in entries if isinstance(e.get("bytes"), int)),
    }
    path = problem_dir / "data" / "MANIFEST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def download_tracebind_print_model() -> None:
    print("\n=== TraceBIND PRINT dependency ===")
    problem_dir = PROBLEMS / "s41467-026-73164-3_tracebind-atac-footprinting"
    url = "https://github.com/HYsxe/PRINT/raw/main/data/shared/Tn5_NN_model.h5"
    dest = problem_dir / "data" / "external" / "print" / "Tn5_NN_model.h5"
    try:
        size = download_file(url, dest)
        print(f"  OK Tn5_NN_model.h5: {fmt_bytes(size)}")
        merge_manifest(
            problem_dir,
            [{"source": "print", "file": str(dest.relative_to(problem_dir)), "bytes": size, "url": url}],
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  FAIL PRINT model: {exc}")


def download_soil_fticr_preprocess_zenodo() -> None:
    print("\n=== Soil FTICR preprocess zenodo ===")
    problem_dir = PROBLEMS / "s41467-026-71453-5_soil-metagenome-fticr-integration"
    entries = download_zenodo("18749196", problem_dir / "data" / "zenodo")
    for e in entries:
        print(f"  OK {e['file'].split('/')[-1]}: {fmt_bytes(e['bytes'])}")
    merge_manifest(problem_dir, entries)


def main() -> None:
    download_soil_supplementary()
    download_soil_fticr_preprocess_zenodo()
    download_tracebind_print_model()
    download_s41586()
    download_s41589()
    print("\nDone.")


if __name__ == "__main__":
    main()
