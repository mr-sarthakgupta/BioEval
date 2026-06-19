# s41467-026-73164-3_tracebind-atac-footprinting

**Title:** Robust footprinting with sample-specific Tn5 bias correction for bulk and single cell ATAC-seq (TraceBIND)  
**DOI:** [10.1038/s41467-026-73164-3](https://doi.org/10.1038/s41467-026-73164-3)

## Layout

```
s41467-026-73164-3_tracebind-atac-footprinting/
├── README.md          # this file
├── paper/             # article PDF
├── repo/              # analysis code (git submodule)
└── data/              # downloaded datasets and manifests
    ├── zenodo/
    ├── figshare/
    ├── nature-supplementary/
    ├── metadata/      # accession lists, API snapshots
    ├── external/      # third-party portals (DepMap, EMSL, etc.)
    ├── sra/           # SRA manifests and download scripts
    └── MANIFEST.json  # download log with sizes
```

## Repositories

- `repo` → https://github.com/lyx-lin/TraceBIND.git

## Dataset notes

- Benchmark GEO series: GSE195460, GSE151302, GSE115098, GSE232222, GSE195443, GSE220289
- Tutorial data: see data/external/dropbox/
- ENCODE CTCF ChIP/degron benchmarks referenced in paper
