# Promotion gate

The observation-only scope is runnable, but this problem remains conditional.
Promote a global-aggregation scope only when all conditions below are met:

- [ ] An input-only river-reach geometry/covariate bundle is reconstructed from
      sources that predate the target's earliest public footprint.
- [ ] Every included field has provenance, license, release date, size, and SHA-256.
- [ ] The bundle contains no target predictions, diagnostics, uncertainty products,
      feature importance, fitted parameters, figure tables, or paper-derived labels.
- [ ] Reach area and upscaling logic are independently implemented and reviewed.
- [ ] Hidden synthetic and geographic-block tests recover known totals without
      consulting Zenodo `7733604` or `8108959`.
- [ ] Resource-bounded staging and leak-guard tests pass.
- [ ] A blinded reviewer confirms that the 27.9 Tg per year result is not encoded in
      any granted file or prompt.
