# Time-resolved single-cell structure during mouse development

Conditional label-free trajectory pilot.

The staged bundle contains a deterministic 2,048-cell by 2,108-gene sparse
count pilot. Every retained gene is detected in at least one percent of cells;
author cell labels, embeddings, markers, transport maps,
pseudotime, and trajectories are blocked. One complete sample per numeric
developmental stage is a fixed hidden holdout; source-sample ordinality, batch,
stage, and Theiler labels are removed from its grantable metadata.

The evaluator checks holdout coverage and RMSE against hidden times and requires
performance within five percent of a frozen five-nearest-pseudobulk expression
baseline. State graphs and full-atlas taxonomy are deliberately outside this
bounded task because they are not independently hard-gated.

See `PROMOTION_CHECKLIST.md` and `curated/acquisition_profiles.yaml`.
