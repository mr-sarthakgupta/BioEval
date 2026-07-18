# Sequence diversity among uncultivated human-gut microbial genomes

Acquisition-only sequence-clustering candidate.

The host-only ENA audit inventory contains 2,058 representative sequence sets.
A deterministic 256-genome pilot may be built for provenance review, but these
genomes are the authors' one-per-discovered-OTU representatives. Anonymization
does not remove that answer-bearing selection, so the inventory, mappings,
metadata, and optional FASTA live only under `evaluator/host-audit/`, outside
the container-mounted `data/` and `curated/` roots.

Author taxonomy, species clusters, trees, novelty labels, functions, abundance,
geography, phenotype, and disease associations are blocked. The pre-clustering
60,664-MAG archive is 40,451,655,328 compressed bytes and exceeds the current
harness budget. Reconsider this problem only after an unbiased bounded pilot,
frozen reference panel, ANI tooling, and hidden clustering fixtures pass review.

The existing host-only inventory can be rebuilt for provenance:

```bash
python scripts/build_gut_mag_manifest.py
```

See `PROMOTION_CHECKLIST.md` before downloading sequences or changing status.
