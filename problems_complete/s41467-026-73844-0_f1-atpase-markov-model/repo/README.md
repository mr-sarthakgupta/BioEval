# A Toolkit for the Markovian Modeling, Simulation, and Analysis of  Rotary Molecular Motors

**This repository contains the source code for the paper:**
- **Title:** A Minimal Chemo-mechanical Markov Model for Rotary Catalysis of $F_1$-ATPase
- **Authors:** Yixin Chen, Helmut Grubmüller
- **BioRxiv:** [https://www.biorxiv.org/content/10.1101/2025.06.26.661389v1](https://www.biorxiv.org/content/10.1101/2025.06.26.661389v1)
- **InReview** [https://www.researchsquare.com/article/rs-7011078/v1](https://www.researchsquare.com/article/rs-7011078/v1)

## Overview

This toolkit provides a suite of tools for studying the rotary molecular motor $F_1$-ATPase, covering:
1. **Bayesian Parameter Search:** Searching for optimal Markov model parameters given experimental training data.
2. **Markov Model Prediction:** Calculating steady-state model predictions (e.g., titration curves) using given parameters.
3. **Kinetic Monte Carlo (KMC) Simulation:** Simulating rotational trajectories using the derived Markov models.
4. **Hidden Markov Analysis (HMA):** Analyzing simulated or experimental trajectories to extract kinetic rates and identify sub-steps.

## Prerequisites

- **Operating System:** Linux is recommended for the C-based modules (`BayesianTraining`, `KineticMonteCarloSimulations`) to facilitate compilation and parallel execution via shell scripts. The Python-based modules (`MarkovModelPrediction`, `HiddenMarkovAnalysis`) are cross-platform and can be used on Windows, macOS, and Linux.
- **Compilers:** `gcc` (version 7.0 or higher recommended) is required for compiling the C source code.
- **Python Environment:** Python 3.8+ is required. The following library versions are recommended:
  - `numpy` (>= 1.20)
  - `scipy` (>= 1.7)
  - `matplotlib` (>= 3.4)
  - `notebook` (for Jupyter support)
  ```bash
  pip install numpy scipy matplotlib notebook
  ```
- **Jupyter Notebook:** Highly recommended for interactive data preparation and analysis. If Jupyter is not available, the code blocks inside the notebooks can be extracted to Python scripts and executed directly.

---

## 1. BayesianTraining

**Correspondence:** This module implements the Bayesian training approach described in the paper for parameter searching.

### Features
- Search for optimal free energies and transition barriers.
- Incorporate experimental titration curves and hydrolysis rates as constraints.
- Support for both 3-conformation and 4-conformation model variants.

### Workflow
1. **Prepare Input:** Use [BayesianTraining/config_input_file/runme.ipynb](BayesianTraining/config_input_file/runme.ipynb) to generate a `.input` configuration file.
2. **Compile:** Navigate to [BayesianTraining/C_source_code/](BayesianTraining/C_source_code/) and run:
   ```bash
   chmod +x compile.sh
   ./compile.sh
   ```
   This produces `run_bayes_3conf` and `run_bayes_4conf`. Compilation typically completes in less than 1 minute.
3. **Execute Search:** 
   - Copy the executable and the `.input` file to [BayesianTraining/workdir/template/](BayesianTraining/workdir/template/).
   - Place a file named `F1-ATPase.bind.csv` in the same directory to include experimental titration curves as training data if applicable. Some experimental titration curves are provided in [BayesianTraining/input_data](BayesianTraining/input_data/) for convenience. 
     > **Reference:** Mao HZ, Gray WD, Weber J. *Does F1-ATPase have a catalytic site that preferentially binds MgADP?* **FEBS Lett.** 2006 Jul 24;580(17):4131-5. [doi: 10.1016/j.febslet.2006.06.059](https://doi.org/10.1016/j.febslet.2006.06.059).
   - Run the parallel chain script from [BayesianTraining/workdir/](BayesianTraining/workdir/):
     ```bash
     chmod +x runme.sh
     ./runme.sh <start_chain_index> <number_of_chains>
     ```

---

## 2. MarkovModelPrediction

**Correspondence:** This module facilitates the calculation of various steady-state model predictions (e.g., titration curves) using a set of given model parameters.

### Features
- Compute steady-state properties over a wide range of nucleotide concentrations.
- Generate predictions for multiple parameter sets (e.g., selected samples from Bayesian training).
- Support for different model variants (e.g., 3-conformation or 4-conformation).

### Workflow
Navigate to [MarkovModelPrediction/PerformPrediction](MarkovModelPrediction/PerformPrediction).
1. **Prepare Parameter File:** Ensure you have a `.sample.csv` or similar parameter file (typically obtained from the `BayesianTraining` module).
2. **Execute Analysis:** Use the Jupyter Notebook [runme.ipynb](MarkovModelPrediction/PerformPredictions/runme.ipynb).
   - Open the notebook and modify the variables in the **Configuration Center** cell.
   - Variables include `confs`, `v_index`, `activeConfs`, `N_param`, `param_file`, and `work_dir_path`.
   - Run all cells to generate the predictions.

**Example/Demo:**
- A sample parameter file is provided as [trained_parameters.sample.csv](MarkovModelPrediction/PerformPredictions/example/trained_parameters.sample.csv).
- The [runme.ipynb](MarkovModelPrediction/PerformPredictions/runme.ipynb) is pre-configured to use this sample file and output results to `./example/output`, allowing you to run a demo immediately by executing all cells in the notebook.

Predicting a titration curve for one parameter set typically takes a few seconds on a modern laptop.

### Plotting and Visualization
Navigate to [MarkovModelPrediction/PlotScripts](MarkovModelPrediction/PlotScripts). 
This submodule provides tools to visualize the calculated model predictions (e.g., turnover rates, efficiencies, titration curves, and beta-subunit configuration populations). The input prediction data for these plots can be directly generated using the scripts in the [PerformPrediction](#workflow) section above.

**Example/Demo:**
- An example set of predictions is provided in `example/input`. These files were directly generated using the scripts in [MarkovModelPrediction/PerformPredictions](MarkovModelPrediction/PerformPredictions).
- You can directly run the Jupyter Notebook [runme.ipynb](MarkovModelPrediction/PlotScripts/runme.ipynb) to visualize these example results. 
- The generated figures will be stored in `example/output`.

---

## 3. KineticMonteCarloSimulations

**Correspondence:** This module generates the KMC simulations of the $F_1$-ATPase central stalk rotation reported in the paper.

### Features
- Physically grounded rotation simulations including flexible spring potentials.
- Support for varied nucleotide concentrations (ATP/product).

### Workflow
1. **Compile:** Navigate to [KineticMonteCarloSimulations/C_source_code/](KineticMonteCarloSimulations/C_source_code/) and run:
   ```bash
   chmod +x compile.sh
   ./compile.sh
   ```
   This produces `run_HMC_3conf` and `run_HMC_4conf`. Compilation typically completes in less than 1 minute.
2. **Setup Workdir:** Copy the executable to [KineticMonteCarloSimulations/workdir/template/](KineticMonteCarloSimulations/workdir/template/).
3. **Configure Batch:** Navigate to [KineticMonteCarloSimulations/workdir/config_input_file/](KineticMonteCarloSimulations/workdir/config_input_file/), provided a `.summary.csv` containing your target parameter sets, and use `runme.py` to generate the simulation inputs.
4. **Run Simulation:** From [KineticMonteCarloSimulations/workdir/](KineticMonteCarloSimulations/workdir/):
   ```bash
   chmod +x runme.sh
   ./runme.sh
   ```

---

## 4. HiddenMarkovAnalysis

**Correspondence:** This module implements the HMA approach for identifying substeps and kinetics in rotational trajectories (see Methods and Supplementary Note 6).

**Note on Implementation:** While the von Mises distribution rigorously describes circular statistics in the theoretical framework (Supplementary Note 6), this codebase implements a robust, functionally equivalent approximation using a wrapped/periodic Gaussian distribution. Because the single-molecule experiments show highly concentrated probability distributions of the F1-ATPase rotational dwells (small angular variances), this approximation ensures numerical stability and computational efficiency while preventing modified Bessel function overflow anomalies during extensive Baum-Welch EM iterations.

### Features
- Automated identification of dwelling times and step sizes from noisy data.
- Expectation-Maximization (EM) optimization for HMM transition probabilities.

### Workflow
1. **Data Preparation:** Use `.rec.csv` files (as generated by the KMC module or from experimental sources).
2. **Analyze:** Open and execute [HiddenMarkovAnalysis/run_HMA.ipynb](HiddenMarkovAnalysis/run_HMA.ipynb). The notebook orchestrates the analysis using core modules like `hmm_expectation.py` and `hmm_maximization.py`.

---

## License

This project is licensed under the [LICENSE](LICENSE) file (MIT license).
