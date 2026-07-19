# Analysis Code — Condensate Miscibility Study

This repository contains the analysis scripts accompanying the manuscript. All scripts reproduce specific figures from the paper and are self-contained given the required input data file.

---

## Repository Structure

```
├── AnalysisInputData.xlsx                # All input data for all scripts (single file)
├── miscibility_GMM_threshold_classification.py
├── global_spearman_miscibility.py
├── IDR_miscibility_hierarchical_cluster_heatmap.py
├── perprotein_spearman_miscibility.py
├── phosphorylation_SaPS_phase_separation_analysis.py
├── ROC_miscibility_transcription_activity_prediction.py
└── README.md
```

---

## Setup

### Requirements

```
python >= 3.9
numpy
pandas
matplotlib
scipy
scikit-learn
statsmodels
openpyxl
```

Install all dependencies:

```bash
pip install numpy pandas matplotlib scipy scikit-learn statsmodels openpyxl
```

### Data File

Place `AnalysisInputData.xlsx` in the **same directory** as the Python scripts. All scripts use relative paths and will locate it automatically.

`AnalysisInputData.xlsx` contains the following sheets:

| Sheet | Used by scripts |
|-------|----------------|
| `IDR_Pair_Miscibility(Fig1b)` | 1, 2, 3, 4 |
| `AA_composition_(28_IDRs)` | 2, 3, 4 |
| `Protein_PS_Predict` | 5 |
| `High_Phosph_for_GO` | 5 |
| `Core_Splicing_Protein` | 5 |
| `Dual-Luc-Assay(Fig6a)` | 6 |
| `ROC_input_21IDRs(Fig6e,f)` | 6 |

---

## Scripts

### 1. `miscibility_GMM_threshold_classification.py`

Fits a two-component Gaussian Mixture Model (GMM) to 378 pairwise miscibility scores to determine the miscible/immiscible classification threshold (r ≈ 0.45).

- **Reproduces:** Extended Data Fig. 1j
- **Input:** `AnalysisInputData.xlsx` — sheet `IDR_Pair_Miscibility(Fig1b)`
- **Output:** `GMM_miscibility_threshold/`

```bash
python miscibility_GMM_threshold_classification.py
```

---

### 2. `global_spearman_miscibility.py`

Computes global Spearman correlations between 26 amino acid compositional features and pairwise miscibility across all 378 IDR pairs. Produces a bar chart colored by −log10(FDR).

- **Reproduces:** Fig. 1f
- **Input:** `AnalysisInputData.xlsx`
  - sheet `IDR_Pair_Miscibility(Fig1b)`
  - sheet `AA_composition_(28_IDRs)`
- **Output:** `global_spearman_miscibility/`

```bash
python global_spearman_miscibility.py
```

---

### 3. `IDR_miscibility_hierarchical_cluster_heatmap.py`

Performs hierarchical clustering of 28 IDRs based on their pairwise miscibility profiles. Produces a dendrogram, intra-cluster miscibility boxplot, and amino acid composition heatmap.

- **Reproduces:** Extended Data Fig. 3a, 3b, 3c
- **Input:** `AnalysisInputData.xlsx`
  - sheet `IDR_Pair_Miscibility(Fig1b)`
  - sheet `AA_composition_(28_IDRs)`
- **Output:** `IDR_hierarchical_clustering/`

```bash
python IDR_miscibility_hierarchical_cluster_heatmap.py
```

---

### 4. `perprotein_spearman_miscibility.py`

Computes per-protein Spearman correlations (each of 28 proteins vs. its 27 partners) between partner amino acid features and miscibility. Identifies FYW-positive and EDKRH-negative protein groups and compares their amino acid compositions.

- **Reproduces:** Extended Data Fig. 4b, 4c, 4d
- **Input:** `AnalysisInputData.xlsx`
  - sheet `IDR_Pair_Miscibility(Fig1b)`
  - sheet `AA_composition_(28_IDRs)`
- **Output:** `perprotein_spearman_miscibility/`

```bash
python perprotein_spearman_miscibility.py
```

---

### 5. `phosphorylation_SaPS_phase_separation_analysis.py`

Analyzes the relationship between serine/tyrosine phosphorylation and phase separation propensity (SaPS score). Compares WT vs. phosphorylated SaPS scores and visualizes S+Y fraction vs. phosphorylation level.

- **Reproduces:** Fig. 5b, 5c, 5e
- **Input:** `AnalysisInputData.xlsx`
  - sheet `Protein_PS_Predict`
  - sheet `High_Phosph_for_GO`
  - sheet `Core_Splicing_Protein`
- **Output:** `phosphorylation_phase_separation_analysis/`

```bash
python phosphorylation_SaPS_phase_separation_analysis.py
```

---

### 6. `ROC_miscibility_transcription_activity_prediction.py`

Performs ROC/AUC analysis to assess the predictive relationship between Pol II nuclear miscibility and transcriptional activity.
- Task A: Pol II miscibility predicts Activation/Repression class (Fig. 6e)
- Task B: Transcriptional activity predicts High/Low miscibility class (Fig. 6f)

- **Reproduces:** Fig. 6e, 6f
- **Input:** `AnalysisInputData.xlsx`
  - sheet `ROC_input_21IDRs(Fig6e,f)`
- **Output:** `ROC_miscibility_transcription_activity/`

```bash
python ROC_miscibility_transcription_activity_prediction.py
```

---

## Notes

- All scripts write output to a subdirectory created automatically in the same folder as the script.
- PDF figures and Excel result files are generated for each analysis.
- Scripts are independent and can be run in any order.
