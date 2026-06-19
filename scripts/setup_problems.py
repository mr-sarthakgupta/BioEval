#!/usr/bin/env python3
"""Create per-paper problem folders, download data, and write manifests."""

from __future__ import annotations

import csv
import io
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path("/home/mrsar/paper-invert")
PROBLEMS = ROOT / "problems"
PAPERS = ROOT / "papers"

UA = "paper-invert/1.0"


@dataclass
class ZenodoAsset:
    record_id: str
    subdir: str | None = None


@dataclass
class UrlAsset:
    url: str
    filename: str
    subdir: str = "nature-supplementary"


@dataclass
class FigshareAsset:
    article_id: int
    subdir: str = "figshare"


@dataclass
class Problem:
    problem_id: str
    title: str
    doi: str
    pdf_name: str
    repos: list[tuple[str, str]]  # (submodule_path_relative_to_problem, git_url)
    zenodo: list[ZenodoAsset] = field(default_factory=list)
    figshare: list[FigshareAsset] = field(default_factory=list)
    urls: list[UrlAsset] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


PROBLEM_DEFS: list[Problem] = [
    Problem(
        problem_id="s41467-026-73844-0_f1-atpase-markov-model",
        title="A minimal chemo-mechanical Markov model for rotary catalysis of F1-ATPase",
        doi="10.1038/s41467-026-73844-0",
        pdf_name="s41467-026-73844-0.pdf",
        repos=[("repo", "https://github.com/YixinChen95/MarkovianF1.git")],
        zenodo=[ZenodoAsset("19133448")],
        notes=[
            "Experimental titration curves are also bundled in repo/BayesianTraining/input_data/.",
        ],
    ),
    Problem(
        problem_id="s41467-026-71453-5_soil-metagenome-fticr-integration",
        title="Continental-scale integration of soil metagenomes and organic matter chemistry",
        doi="10.1038/s41467-026-71453-5",
        pdf_name="s41467-026-71453-5.pdf",
        repos=[
            ("repo/analysis", "https://github.com/EMSL-MONet/The-1000-Soil-ICR-Metagenome.git"),
            ("repo/preprocessing", "https://github.com/osumpcheng/FTICR_preprocess.git"),
        ],
        zenodo=[
            ZenodoAsset("18747539"),
            ZenodoAsset("7406532"),
            ZenodoAsset("15328215"),
        ],
        urls=[
            UrlAsset(
                "https://www.nature.com/articles/s41467-026-71453-5#Sec31",
                "data-availability.html",
                "metadata",
            ),
        ],
        notes=[
            "Raw metagenome FASTQ: SRA PRJNA1260013 (~270 GB) — see data/sra/PRJNA1260013/",
            "Raw FTICR-MS: EMSL portal project 60141 — see data/external/emsl/",
            "MONet portal: https://sc-data.emsl.pnnl.gov/monet",
            "NMDC study: nmdc:sty-11-28tm5d36",
        ],
    ),
    Problem(
        problem_id="s41467-026-73635-7_butterfly-longevity-pollen-feeding",
        title="Evolution of increased longevity and slowed ageing in a genus of tropical butterfly",
        doi="10.1038/s41467-026-73635-7",
        pdf_name="s41467-026-73635-7.pdf",
        repos=[],
        figshare=[FigshareAsset(31081597)],
        urls=[
            UrlAsset(
                "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-73635-7/MediaObjects/41467_2026_73635_MOESM6_ESM.zip",
                "source-data.zip",
            ),
            UrlAsset(
                "https://static-content.springer.com/esm/art%3A10.1038%2Fs41467-026-73635-7/MediaObjects/41467_2026_73635_MOESM3_ESM.xlsx",
                "supplementary-data.xlsx",
            ),
        ],
        notes=["No dedicated analysis repository; statistics reproducible from source data."],
    ),
    Problem(
        problem_id="s41467-026-73164-3_tracebind-atac-footprinting",
        title="Robust footprinting with sample-specific Tn5 bias correction for bulk and single cell ATAC-seq (TraceBIND)",
        doi="10.1038/s41467-026-73164-3",
        pdf_name="s41467-026-73164-3.pdf",
        repos=[("repo", "https://github.com/lyx-lin/TraceBIND.git")],
        zenodo=[ZenodoAsset("19446219")],
        notes=[
            "Benchmark GEO series: GSE195460, GSE151302, GSE115098, GSE232222, GSE195443, GSE220289",
            "Tutorial data: see data/external/dropbox/",
            "ENCODE CTCF ChIP/degron benchmarks referenced in paper",
        ],
    ),
    Problem(
        problem_id="s41467-026-73977-2_forge-cancer-drug-response",
        title="Gene dependency-informed inference of response to targeted cancer therapies (FORGE)",
        doi="10.1038/s41467-026-73977-2",
        pdf_name="s41467-026-73977-2.pdf",
        repos=[("repo", "https://github.com/sreerampeela/FORGE.git")],
        zenodo=[ZenodoAsset("19491795")],
        figshare=[FigshareAsset(31268542)],
        notes=[
            "DepMap Public 24Q4: https://depmap.org/portal/ — see data/external/depmap/",
            "CREAMMIST: https://creammist.mtms.dev/ — curated subset included in Figshare bundle",
        ],
    ),
]

TRACE_BIND_GEO = [
    "GSE195460",
    "GSE151302",
    "GSE115098",
    "GSE232222",
    "GSE195443",
    "GSE220289",
]

DEPMAP_FILES = [
    "CRISPRGeneEffect.csv",
    "CRISPRGeneDependency.csv",
    "OmicsExpressionProteinCodingGenesTPMLogp1.csv",
    "OmicsExpressionRNASeQGeneTPMLogp1.csv",
]


def fmt_bytes(n: int | float | None) -> str:
    if n is None:
        return "unknown"
    n = float(n)
    if n >= 1024**4:
        return f"{n / 1024**4:.2f} TB"
    if n >= 1024**3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024**2:
        return f"{n / 1024**2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n:.0f} B"


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


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
    meta = fetch_json(f"https://zenodo.org/api/records/{record_id}")
    out: list[dict] = []
    target = dest_dir / record_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for f in meta.get("files", []):
        url = f["links"]["self"]
        name = f["key"]
        size = download_file(url, target / name)
        out.append({"source": "zenodo", "record_id": record_id, "file": name, "bytes": size})
    return out


def download_figshare(article_id: int, dest_dir: Path) -> list[dict]:
    meta = fetch_json(f"https://api.figshare.com/v2/articles/{article_id}")
    out: list[dict] = []
    target = dest_dir / str(article_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    for f in meta.get("files", []):
        url = f["download_url"]
        name = f["name"]
        size = download_file(url, target / name)
        out.append({"source": "figshare", "article_id": article_id, "file": name, "bytes": size})
    return out


def write_readme(problem: Problem, path: Path) -> None:
    lines = [
        f"# {problem.problem_id}",
        "",
        f"**Title:** {problem.title}  ",
        f"**DOI:** [{problem.doi}](https://doi.org/{problem.doi})",
        "",
        "## Layout",
        "",
        "```",
        f"{problem.problem_id}/",
        "├── README.md          # this file",
        "├── paper/             # article PDF",
        "├── repo/              # analysis code (git submodule)",
        "└── data/              # downloaded datasets and manifests",
        "    ├── zenodo/",
        "    ├── figshare/",
        "    ├── nature-supplementary/",
        "    ├── metadata/      # accession lists, API snapshots",
        "    ├── external/      # third-party portals (DepMap, EMSL, etc.)",
        "    ├── sra/           # SRA manifests and download scripts",
        "    └── MANIFEST.json  # download log with sizes",
        "```",
        "",
        "## Repositories",
        "",
    ]
    if problem.repos:
        for rel, url in problem.repos:
            lines.append(f"- `{rel}` → {url}")
    else:
        lines.append("- None (data-only reproduction)")
    lines.extend(["", "## Dataset notes", ""])
    for note in problem.notes:
        lines.append(f"- {note}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_manifest(problem_dir: Path, entries: list[dict]) -> None:
    manifest = {
        "problem_id": problem_dir.name,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "entries": entries,
        "total_bytes": sum(e.get("bytes", 0) for e in entries if isinstance(e.get("bytes"), int)),
    }
    (problem_dir / "data" / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )


def build_sra_manifest(problem_dir: Path) -> list[dict]:
    project = "PRJNA1260013"
    out_dir = problem_dir / "data" / "sra" / project
    out_dir.mkdir(parents=True, exist_ok=True)

    with urllib.request.urlopen(
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=sra&term={project}&retmax=200&retmode=json"
    ) as resp:
        ids = json.load(resp)["esearchresult"]["idlist"]

    runs: list[dict] = []
    total_mb = 0.0
    for i in range(0, len(ids), 50):
        batch = ",".join(ids[i : i + 50])
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            f"?db=sra&id={batch}&rettype=runinfo&retmode=csv"
        )
        with urllib.request.urlopen(url, timeout=120) as resp:
            for line in resp.read().decode().strip().splitlines():
                parts = line.split(",")
                if not parts[0].startswith("SRR"):
                    continue
                size_mb = float(parts[7]) if parts[7] else 0.0
                total_mb += size_mb
                runs.append(
                    {
                        "run": parts[0],
                        "sample": parts[24] if len(parts) > 24 else "",
                        "size_mb": size_mb,
                        "download_path": parts[9] if len(parts) > 9 else "",
                    }
                )
        time.sleep(0.34)

    runs_path = out_dir / "runs.json"
    runs_path.write_text(json.dumps(runs, indent=2), encoding="utf-8")

    script = out_dir / "download.sh"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                f'OUTDIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)/fastq"',
                'mkdir -p "$OUTDIR"',
                'command -v prefetch >/dev/null || { echo "Install NCBI sra-tools (prefetch/fasterq-dump)"; exit 1; }',
                f"# Total estimated size: {fmt_bytes(int(total_mb * 1024 * 1024))} ({len(runs)} runs)",
                'while read -r run; do',
                '  [[ -z "$run" || "$run" == "#"* ]] && continue',
                '  echo "Downloading $run ..."',
                '  prefetch "$run" -O "$OUTDIR"',
                '  fasterq-dump "$OUTDIR/$run" -O "$OUTDIR" --split-files',
                'done < runs.txt',
                "",
            ]
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)
    (out_dir / "runs.txt").write_text("\n".join(r["run"] for r in runs) + "\n", encoding="utf-8")

    readme = out_dir / "README.md"
    readme.write_text(
        "\n".join(
            [
                f"# SRA {project}",
                "",
                f"- **Runs:** {len(runs)}",
                f"- **Estimated size:** {fmt_bytes(int(total_mb * 1024 * 1024))}",
                "- **Not downloaded automatically** (too large for default setup).",
                "",
                "To download:",
                "```bash",
                "./download.sh",
                "```",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return [
        {
            "source": "sra",
            "project": project,
            "file": "runs.json",
            "bytes": runs_path.stat().st_size,
            "estimated_total_bytes": int(total_mb * 1024 * 1024),
            "downloaded": False,
        }
    ]


def build_geo_manifest(problem_dir: Path) -> list[dict]:
    out_dir = problem_dir / "data" / "metadata" / "geo"
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for gse in TRACE_BIND_GEO:
        url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gse}&targ=self&form=text&view=brief"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            text = resp.read().decode("utf-8", "replace")
        path = out_dir / f"{gse}.soft"
        path.write_text(text, encoding="utf-8")
        entries.append({"source": "geo", "accession": gse, "file": str(path.relative_to(problem_dir)), "bytes": path.stat().st_size})
    (out_dir / "accessions.txt").write_text("\n".join(TRACE_BIND_GEO) + "\n", encoding="utf-8")
    return entries


def build_external_manifests(problem: Problem, problem_dir: Path) -> list[dict]:
    entries: list[dict] = []

    if "forge" in problem.problem_id:
        depmap_dir = problem_dir / "data" / "external" / "depmap"
        depmap_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# DepMap Public 24Q4",
            "",
            "Portal: https://depmap.org/portal/download/all/",
            "",
            "Suggested files for FORGE reproduction:",
        ]
        for fn in DEPMAP_FILES:
            lines.append(f"- {fn}")
        lines.extend(
            [
                "",
                "Note: Processed Dep/Exp matrices are included in data/figshare/31268542/.",
                "",
                "Example download (requires accepting DepMap license in browser first):",
                "https://depmap.org/portal/download/api/file/depmap-public/<filename>",
                "",
            ]
        )
        readme = depmap_dir / "README.md"
        readme.write_text("\n".join(lines), encoding="utf-8")
        entries.append({"source": "depmap", "file": "external/depmap/README.md", "bytes": readme.stat().st_size, "downloaded": False})

    if "soil-metagenome" in problem.problem_id:
        emsl_dir = problem_dir / "data" / "external" / "emsl"
        emsl_dir.mkdir(parents=True, exist_ok=True)
        readme = emsl_dir / "README.md"
        readme.write_text(
            "\n".join(
                [
                    "# EMSL / MONet data portals",
                    "",
                    "- Raw FTICR-MS (project 60141): https://sc-data.emsl.pnnl.gov/?projectId=60141",
                    "- MONet open science: https://sc-data.emsl.pnnl.gov/monet",
                    "- NMDC study: https://data.microbiomedata.org/details/study/nmdc:sty-11-28tm5d36",
                    "",
                    "Portal-hosted raw data is not bulk-downloaded automatically.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        entries.append({"source": "emsl", "file": "external/emsl/README.md", "bytes": readme.stat().st_size, "downloaded": False})

    if "tracebind" in problem.problem_id:
        dropbox_dir = problem_dir / "data" / "external" / "dropbox"
        dropbox_dir.mkdir(parents=True, exist_ok=True)
        url = "https://www.dropbox.com/scl/fo/zhmxfp0gxnmlgeo8jsmbv/AO3I75Lz6eP3Illn-eb0Zgc?rlkey=zkfi6c7c29eb11tbmcz80n8sf&dl=1"
        try:
            size = download_file(url, dropbox_dir / "tracebind-tutorial-archive.zip")
            entries.append(
                {
                    "source": "dropbox",
                    "file": "external/dropbox/tracebind-tutorial-archive.zip",
                    "bytes": size,
                    "url": url,
                }
            )
        except urllib.error.HTTPError as exc:
            readme = dropbox_dir / "README.md"
            readme.write_text(
                f"Automatic download failed ({exc}). Manual URL:\n{url}\n",
                encoding="utf-8",
            )
            entries.append({"source": "dropbox", "file": "external/dropbox/README.md", "bytes": readme.stat().st_size, "downloaded": False, "url": url})

    return entries


def setup_problem(problem: Problem) -> list[dict]:
    problem_dir = PROBLEMS / problem.problem_id
    (problem_dir / "paper").mkdir(parents=True, exist_ok=True)
    (problem_dir / "data").mkdir(parents=True, exist_ok=True)

    src_pdf = PAPERS / problem.pdf_name
    dst_pdf = problem_dir / "paper" / problem.pdf_name
    if src_pdf.exists():
        shutil.copy2(src_pdf, dst_pdf)
    elif not dst_pdf.exists():
        raise FileNotFoundError(f"Missing PDF: {src_pdf}")

    write_readme(problem, problem_dir / "README.md")

    entries: list[dict] = [
        {
            "source": "paper",
            "file": f"paper/{problem.pdf_name}",
            "bytes": dst_pdf.stat().st_size,
        }
    ]

    for asset in problem.zenodo:
        sub = PROBLEMS / problem.problem_id / "data" / "zenodo"
        entries.extend(download_zenodo(asset.record_id, sub))

    for asset in problem.figshare:
        sub = PROBLEMS / problem.problem_id / "data" / "figshare"
        entries.extend(download_figshare(asset.article_id, sub))

    for asset in problem.urls:
        if asset.filename.endswith(".html"):
            continue
        dest = problem_dir / "data" / asset.subdir / asset.filename
        try:
            size = download_file(asset.url, dest)
            entries.append({"source": asset.subdir, "file": str(dest.relative_to(problem_dir)), "bytes": size, "url": asset.url})
        except Exception as exc:  # noqa: BLE001
            entries.append({"source": asset.subdir, "file": asset.filename, "bytes": 0, "url": asset.url, "error": str(exc)})

    if "soil-metagenome" in problem.problem_id:
        entries.extend(build_sra_manifest(problem_dir))
        entries.extend(build_external_manifests(problem, problem_dir))
    if "tracebind" in problem.problem_id:
        entries.extend(build_geo_manifest(problem_dir))
        entries.extend(build_external_manifests(problem, problem_dir))
    if "forge" in problem.problem_id:
        entries.extend(build_external_manifests(problem, problem_dir))

    write_manifest(problem_dir, entries)
    return entries


def main() -> int:
    PROBLEMS.mkdir(parents=True, exist_ok=True)
    summary = []
    for problem in PROBLEM_DEFS:
        print(f"Setting up {problem.problem_id} ...")
        entries = setup_problem(problem)
        total = sum(e.get("bytes", 0) for e in entries if isinstance(e.get("bytes"), int))
        summary.append((problem.problem_id, total, len(entries)))
        print(f"  manifest entries: {len(entries)}, downloaded: {fmt_bytes(total)}")

    print("\nSummary:")
    for pid, total, n in summary:
        print(f"  {pid}: {fmt_bytes(total)} across {n} manifest entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
