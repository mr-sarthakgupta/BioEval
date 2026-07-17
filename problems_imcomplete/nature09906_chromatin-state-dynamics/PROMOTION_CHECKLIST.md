# Promotion gate

- [ ] All 178 core BED files match the tracked names and compressed byte sizes.
- [ ] All 19 CEL files match the validation manifest.
- [ ] The full acquired bundle passes the leak guard with zero segmentation, state
      label, mnemonic, posterior, emission, transition, or model files.
- [ ] hg18 reference assets and every external annotation have a release date no
      later than 2011-01-21 plus a pinned checksum.
- [ ] The H1/K562 chr21/chr22 pilot finishes within the declared time, memory, disk,
      and transfer budgets.
- [ ] Pilot tests demonstrate label-invariant state alignment, held-out scoring,
      segmentation stability, and shuffled-track negative controls.
- [ ] The full nine-cell run is resource bounded and reproduces prespecified
      expression and annotation validation metrics without published labels.
