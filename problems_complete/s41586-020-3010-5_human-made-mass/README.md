# Historical material stocks and global living biomass

Active bounded accounting task. Four observation-only inputs are grantable,
while post-2015 trajectories and crossing-year outputs remain blocked.

The staged host-side audit material contains:

- annual material stocks by neutral category for 1900–2015;
- sparse historical global-biomass estimates with source grouping; and
- a neutral field dictionary.

The curated bundle filters post-2015 biomass rows, freezes explicit dry-mass
sensitivity bounds, and is scored by evaluator-side recomputation. Exact
crossing-year recovery remains outside the active scope.
Rebuild the host audit and curated bundle with:

```bash
python scripts/build_human_made_mass_inputs.py /path/to/source-checkout
python scripts/curate_human_made_mass.py
```

See `PROMOTION_CHECKLIST.md` before changing `benchmark_status`.
