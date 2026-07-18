# s41586-022-05383-9_light-competition-plant-diversity

**Title:** Light competition drives herbivore and nutrient effects on plant diversity  
**DOI:** [10.1038/s41586-022-05383-9](https://doi.org/10.1038/s41586-022-05383-9)

## Layout

```
s41586-022-05383-9_light-competition-plant-diversity/
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

- Pinned Dryad version `204170` contains 14 files totaling 1,276,692 bytes.
- The four community and physical-observation files are the future input
  allowlist, but none are grantable until vendored and checksum-verified.
- Trait-response tables, the paper-specific README, and Zenodo `7269719` author
  scripts are blocked as answer-bearing artifacts.
- If acquired, the observations are analysis-ready quadrat summaries rather than
  raw species-cover or sensor streams; any future scope must remain at that level.
- Dryad currently requires an API bearer token for file downloads. Set
  `DRYAD_TOKEN` and rerun `scripts/setup_problems.py --problem-id
  s41586-022-05383-9_light-competition-plant-diversity --profile selective`.
- `curated/source_manifest.json` pins every file ID, size, and SHA-256 independently
  of local download state.
