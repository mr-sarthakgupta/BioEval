# nature09906_chromatin-state-dynamics

**Title:** Mapping and analysis of chromatin state dynamics in nine human cell types  
**DOI:** [10.1038/nature09906](https://doi.org/10.1038/nature09906)

## Layout

```
nature09906_chromatin-state-dynamics/
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

- GEO GSE26386 core ChIP/WCE data remain manifest-only by default.
- All deposited state segmentations, labels and model outputs are blocked.
- `curated/core_bed_manifest.csv` contains exactly 178 common-core BED tracks
  (44,368,287,353 compressed bytes); the two K562-only H3K9me3 tracks are excluded.
- `curated/expression_cel_manifest.csv` pins 19 raw CEL files (49,106,218 bytes).
- `acquire.py` provides `manifest-only`, `pilot`, and `full` profiles. The pilot
  processes one H1/K562 compressed track at a time and retains chr21/chr22 only.
- Coordinates are frozen to hg18. External annotation releases must predate
  2011-01-21.
- This remains conditional until the resource-bounded pilot and full allowlist pass
  `PROMOTION_CHECKLIST.md`.
