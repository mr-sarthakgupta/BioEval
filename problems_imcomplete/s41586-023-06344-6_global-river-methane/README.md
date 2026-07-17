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

- Scoped to held-out concentration, temperature-response and measured diffusive flux.
- The mixed 9.807 GB target archive and all gridded output rasters remain manifest-only and blocked.
- Four GRiMeDB v2 observation tables are pinned to EDI package
  `knb-lter-ntl.420.2` and downloaded locally (11.5 MB total).
- `curated/source_manifest.json` records SHA-256 checksums and
  `curated/source_folds.csv` freezes five literature-source folds.
- The scoped observation analysis is runnable. The folder remains incomplete because
  the global 27.9 Tg per year conclusion is intentionally out of scope until the
  independent aggregation gate in `PROMOTION_CHECKLIST.md` passes.
