# s41586-023-06344-6_global-river-methane

**Title:** Global methane emissions from rivers and streams  
**DOI:** [10.1038/s41586-023-06344-6](https://doi.org/10.1038/s41586-023-06344-6)

## Layout

```
s41586-023-06344-6_global-river-methane/
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

- None (data-only reproduction)

## Dataset notes

- Active bounded scope: deterministic positive-value and source-coverage summaries
  for methane concentration and directly measured diffusive flux.
- The mixed 9.807 GB target archive and all gridded output rasters remain manifest-only and blocked.
- Four GRiMeDB v2 observation tables are pinned to EDI package
  `knb-lter-ntl.420.2` and downloaded locally (11.5 MB total).
- `curated/source_manifest.json` records SHA-256 checksums and
  `curated/source_folds.csv` freezes five literature-source folds.
- `observation_summary.csv` is scored by direct recomputation from the frozen tables.
- The global 27.9 Tg per year conclusion remains intentionally out of scope; the
  optional scope-extension conditions are listed in `PROMOTION_CHECKLIST.md`.
