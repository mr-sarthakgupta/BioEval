# Promotion gate

The bounded label-free pilot is active after deterministic holdout, leakage, and
readiness validation. The remaining items are provenance and independent-review
follow-ups required before expanding beyond the current pilot:

- [ ] Every downloaded file has a pinned URL, byte count, checksum, release
      date, and redistribution review.
- [x] A resource-bounded pilot extracts sparse raw counts without author cell
      calls where technically feasible.
- [x] Cell metadata uses non-ordinal opaque sample/batch IDs; holdout batch,
      developmental time, and Theiler stage are blank.
- [x] Cluster labels, cell types, marker tables, corrected PCA/UMAP, colour
      maps, transport maps, pseudotime, and trajectory outputs are absent.
- [x] Cell IDs are deterministically remapped so repository joins cannot recover
      blocked author annotations.
- [x] A fixed complete-sample holdout exists across numeric developmental stages,
      with its time labels stored evaluator-side only.
- [x] Evaluator fixtures test complete-sample held-out-time prediction against
      a frozen expression baseline and reject mean-time shortcuts.
- [ ] Staging passes leak scans and declared disk, memory, and runtime budgets.
- [ ] A blinded reviewer confirms that exact author taxonomy and trajectories
      cannot be reconstructed by joining granted metadata.
