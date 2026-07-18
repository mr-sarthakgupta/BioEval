# Historical material stocks and global living biomass

Acquisition-only paper-inversion candidate. No data are grantable.

The staged host-side audit material contains:

- annual material stocks by neutral category for 1900–2015;
- sparse historical global-biomass estimates with source grouping; and
- a neutral field dictionary.

The candidate was downgraded because the target-repository workbooks have not
passed an independent provenance review, the biomass table includes post-2015
rows, and the carbon-to-dry-mass conversion and scientific evaluator are not
frozen. Rebuild the audit CSVs from the pinned source checkout:

```bash
python scripts/build_human_made_mass_inputs.py /path/to/source-checkout
```

See `PROMOTION_CHECKLIST.md` before changing `benchmark_status`.
