# s41467-026-71453-5_soil-metagenome-fticr-integration

**Title:** Continental-scale integration of soil metagenomes and organic matter chemistry  
**DOI:** [10.1038/s41467-026-71453-5](https://doi.org/10.1038/s41467-026-71453-5)

## Layout

```
s41467-026-71453-5_soil-metagenome-fticr-integration/
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

- `repo/analysis` → https://github.com/EMSL-MONet/The-1000-Soil-ICR-Metagenome.git
- `repo/preprocessing` → https://github.com/osumpcheng/FTICR_preprocess.git

## Dataset notes

- Raw metagenome FASTQ: SRA PRJNA1260013 (~270 GB) — see data/sra/PRJNA1260013/
- Raw FTICR-MS: EMSL portal project 60141 — see data/external/emsl/
- MONet portal: https://sc-data.emsl.pnnl.gov/monet
- NMDC study: nmdc:sty-11-28tm5d36
