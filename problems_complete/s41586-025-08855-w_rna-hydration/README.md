# Replicated map-density inference around a folded RNA

Conditional map-level structural-biology problem.

The runnable bundle contains four identifier-sanitized half-maps (249 MB total),
a polymer-only RNA scaffold released before the target footprint, and a neutral
map manifest. EMDB labels are removed from the decompressed MRC headers. Target
solvent models are neither acquired nor used for scoring; full maps, validation
products, raw movies/particles, simulations, code, and publications remain
blocked from the evaluated agent.

The scientific evaluator loads the sanitized half-maps, verifies map and
parameter hashes, recomputes local peak density independently in each half, and
requires coordinate replication within and across reconstructions. This bounded
task scores replicated density, not water-versus-ion chemical identity.

Rebuild the scaffold and manifests after acquiring the pinned files:

```bash
python scripts/setup_problems.py --problem-id s41586-025-08855-w_rna-hydration
```

See `PROMOTION_CHECKLIST.md` before changing status.
