# Neutral FORGE inputs

- `drug_target_map.csv` is the unfitted drug-to-gene mapping distributed in the
  study repository's test data. It is needed to align drug IC50 values with target
  dependency columns and contains no model output.
- `cell_line_split.csv` contains the 700 identifiers shared by `Exp.csv`,
  `Dep.csv`, and `Creammist_common_ic50.csv`. For identifier `id`, the test split is
  assigned when the unsigned integer represented by the first eight bytes of
  `SHA256("bioeval-forge-v1:" + id)` is divisible by five; all other rows are train.

The fixed split is an evaluation convention created for BioEval. It is not an
author-provided result and must be applied identically to every submitted method.

- `drug_response_train.csv` contains only training-split IC50 labels.
- `drug_response_test_rows.csv` contains held-out drug/cell-line keys without IC50.
- Duplicate source columns for seven repeated cell-line names are collapsed by their
  arithmetic mean in both partitions.

The corresponding test labels live under `evaluator/`, are non-grantable, and are
joined only by the judge when recomputing submitted prediction metrics. Regenerate
all three tables with `scripts/build_forge_holdout.py`.
