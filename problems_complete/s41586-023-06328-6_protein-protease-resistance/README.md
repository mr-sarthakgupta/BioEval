# s41586-023-06328-6_protein-protease-resistance

**Title:** Mega-scale experimental analysis of protein folding stability in biology and design  
**DOI:** [10.1038/s41586-023-06328-6](https://doi.org/10.1038/s41586-023-06328-6)

## Layout

```
s41586-023-06328-6_protein-protease-resistance/
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

- The intended scope is count-based protease resistance, not absolute thermodynamic
  stability. The active library-1 fold-zero pilot recomputes held-out phenotype
  distributions, replicate agreement, and cross-protease rank correlation.
- Only raw NGS count tables and the optional raw qPCR control are downloaded.
- Selective setup pins Zenodo record `7992926`, downloads
  `Raw_NGS_count_tables.zip` and `Pipeline_qPCR_data.zip`, and extracts only four
  count CSVs plus `Raw_qPCR_data_FigS1.csv`.
- The raw-count ZIP is data-only but is not directly grantable because its expanded
  size exceeds the leak guard's archive scan limit; the extracted CSVs are grantable.
- Fitted K50/delta-G tables, processed datasets, pipelines, figure tables, generated
  AlphaFold structures, and design blueprints are explicitly blocked.
- `curated/source_manifest.json` pins all nine record files and checksums;
  `curated/assay_conditions.csv` provides the neutral 48-column assay map.
