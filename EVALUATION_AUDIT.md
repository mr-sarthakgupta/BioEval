# BioEval Evaluation Audit

**Repository:** `/home/mrsar/paper-invert`  
**Audit date:** 2026-07-15  
**Scope:** benchmark design, problem specifications, data catalogs, evaluator implementation, guardrails, run logs, submitted artifacts, judge outputs, reproducibility, and methodological validity  
**Audit mode:** read-only investigation followed by this report; no benchmark code or run artifacts were changed

---

## 1. Executive conclusion

BioEval is an engineering prototype for **blind paper inversion**: an under-evaluation agent (UEA) receives a de-identified scientific task, requests data through guarded tooling, performs open-world analysis, and submits conclusions. A separate LLM then compares the submission with hidden conclusions from the original paper.

The repository contains several thoughtful components:

- The public task is separated from hidden conclusions and rubrics.
- Data grants pass through catalog policy, staging filters, and a byte-level leak guard.
- Search and webpage traffic can be screened for held-out-paper leakage.
- Runs retain detailed data-request, tool-call, transcript, cost, and model-trace artifacts.

However, the current system is **not yet a scientifically valid or reproducible benchmark**. Its present score does not establish that an agent reproduced a paper's analysis or results. It establishes only that one LLM judge considered the final prose and a truncated transcript sufficiently similar to hidden expected claims.

The most serious problems are:

1. **The sole score is an unconstrained LLM-generated number.** No code recomputes paper metrics, verifies analysis artifacts, or enforces the score formula and verdict thresholds described in the judge prompt.
2. **Data-gate behavior is a major confounder.** Runs succeed or fail depending on traffic-guard decisions, request phrasing, catalog completeness, and staging behavior—not only scientific capability.
3. **Some grants encode the expected answer.** Butterfly summary tables and the historical IDR spreadsheet bundle expose paper-adjacent result structures, reducing discovery to table reading.
4. **Some tasks are infeasible under the current data and compute setup.** F1 lacks a complete constraint bundle; IDR and butterfly catalogs reference missing primary assets.
5. **Actual run handling is unreliable.** Degenerate repeated answers and step-limit boilerplate are accepted, crashes can lose the trace, run status remains `initialized`, and judging is not part of the runner.
6. **The stored scores are selectively produced and statistically uninterpretable.** There are 45 runs with `run_metadata.json`, heavily concentrated on butterfly, but only 6 judge outputs. No repeated-trial protocol, confidence interval, pass@k, model-version freeze, or aggregation exists.

Accordingly:

> Existing `judge_result.json` files should be treated as qualitative case studies, not benchmark measurements. No headline benchmark score is defensible from the current artifacts.

---

## 2. What BioEval is trying to evaluate

The root README describes a paper-inversion task: determine whether an agent can rediscover the central conclusions of a biology paper without receiving the original paper, source repository, expected answer, or benchmark problem folder (`README.md:5-31`).

The intended UEA receives:

- a public `sandbox_prompt`;
- an empty writable workspace;
- internet access through guarded search/fetch tools;
- scientific Python and command-line analysis tools;
- a guarded, structured `design_experiment` interface;
- a disk and resource budget.

The UEA is intended not to receive:

- the held-out paper or supplementary manuscript;
- author source code;
- serialized models;
- expected conclusions or judge rubric;
- hidden catalog paths and grant-denial details;
- paper title, DOI, author names, repository identity, or other leak markers.

The intended construct is therefore not conventional predictive-model accuracy. It is:

> Can an autonomous scientific agent formulate requests, obtain admissible evidence, analyze it, and recover selected hidden paper conclusions under a blind open-world protocol?

This construct combines at least four capabilities:

1. scientific problem interpretation;
2. data discovery and request formulation;
3. computational analysis;
4. conclusion synthesis.

The present benchmark does not isolate these capabilities. A single final score mixes agent competence with planner quality, traffic-guard behavior, catalog quality, missing data, internet availability, runtime stability, and LLM-judge discretion.

---

## 3. Intended end-to-end evaluation flow

```text
problem spec YAML
  ├─ public sandbox_prompt ────────────────┐
  └─ hidden conclusions/rubric/markers ─┐ │
                                       │ │
bioeval-init-run                       │ │
  ├─ TASK.md <─────────────────────────┘ │
  ├─ run_metadata.json                   │
  └─ empty run directories               │
                                         │
bioeval-run-bedrock-uea                   │
  ├─ Docker experiment-agent + UEA        │
  ├─ Bedrock tool-use loop                │
  ├─ guarded web/literature tools         │
  ├─ design_experiment                    │
  │    └─ feasibility → matching → staging → leak guard
  └─ submit_answer                        │
       ├─ final_answer.txt                │
       └─ transcript.txt                  │
                                         │
bioeval-judge <───────────────────────────┘
  ├─ LLM compares prose with hidden targets
  ├─ judge_result.json
  └─ score_history.jsonl
```

The crucial operational fact is that the last stage is **not called by the run orchestrator**. `bioeval-run-bedrock-uea` executes the UEA and exits. An operator must separately run `bioeval-judge`, as documented in `README.md:194-208`.

---

## 4. Problem definition and visibility boundaries

### 4.1 Problem schema

`bioeval/bioeval/schemas.py:126-137` defines each `ProblemSpec`:

- `problem_id`
- `title`
- `doi`
- `sandbox_prompt`
- `expected_conclusions`
- `judge_rubric`
- `expected_caveats`
- `leak_markers`

Only `sandbox_prompt` is intended for the UEA. The rest is evaluator-only metadata.

Problem files are loaded from:

`bioeval/bioeval/problem_specs/*.yaml`

Four specs are present:

1. `butterfly_longevity.yaml`
2. `f1_atpase_markov.yaml`
3. `forge_cancer_response.yaml`
4. `idr_condensate_miscibility.yaml`

### 4.2 Run initialization

`bioeval/bioeval/init_run.py:23-84`:

1. loads `.env`;
2. resolves `problem_id`;
3. loads the hidden problem spec;
4. generates a run ID if one was not supplied;
5. creates:
   - `uea_workspace/`
   - `data_grants/`
   - `results/`
   - `logs/`
6. writes `run_metadata.json`;
7. writes the public prompt to `TASK.md`.

Default run IDs contain:

`UTC timestamp + problem slug + 8 hex characters from uuid4`

See `bioeval/bioeval/run_record.py:16-19`.

The metadata captures:

- run and problem IDs;
- timestamp;
- UEA model;
- selected environment variables;
- git commit and dirty state;
- public prompt;
- output paths.

It initializes `"status": "initialized"` (`init_run.py:36-47`). No lifecycle code updates this field after success, timeout, submission, judge completion, or crash. All inspected runs therefore appear initialized regardless of outcome.

### 4.3 Hidden-title handling

Although the UEA-visible `TASK.md` contains only `sandbox_prompt`, host-side `run_metadata.json` includes the hidden problem title (`init_run.py:71-74`). This is acceptable only because the run root is not exposed to the UEA. It increases the importance of mount isolation and makes these metadata files evaluator-sensitive.

---

## 5. UEA execution in exact detail

### 5.1 Runner

`bioeval/bioeval/run_bedrock_uea.py` performs each problem sequentially:

1. create a fresh run;
2. copy `TASK.md` into the workspace;
3. start Docker Compose services;
4. poll data-agent health every 2 seconds for up to 120 seconds;
5. execute `uea_bedrock_agent` in the UEA container;
6. tear down services unless `--keep-up` is used.

The runner does not:

- judge the run;
- update run status;
- validate that a meaningful answer exists;
- aggregate results;
- retry failed Bedrock calls;
- resume an interrupted agent;
- distinguish a scientific failure from infrastructure failure in a benchmark result.

### 5.2 Model selection and inference settings

The default UEA model is Bedrock Claude Sonnet 4.6:

`us.anthropic.claude-sonnet-4-6`

The model may be overridden through CLI/environment settings. Relevant defaults observed in code and documentation include:

- UEA max steps: 40;
- UEA max output tokens per call: 8192;
- UEA temperature: 0.2;
- Bedrock client total attempts: 1.

The July 3 batch did **not** use the documented 40-step default. `output.txt` shows `--max-steps 1000` for all five problems, including around lines 3575, 6788, 14004, 18100, and 21994. This configuration difference is material and is not represented as a frozen benchmark protocol.

### 5.3 Agent loop

`bioeval/bioeval/container_tools/uea_bedrock_agent.py:423-531` implements the core loop.

For each step:

1. send system prompt, conversation, and tool schemas to Bedrock;
2. record usage/cost;
3. append assistant content to the conversation;
4. inspect returned tool-use blocks;
5. execute each requested tool through local container commands;
6. append tool results;
7. stop when `submit_answer` is called.

There are three automatic termination paths:

1. **Explicit submission:** the model invokes `submit_answer`.
2. **No tool use:** any assistant text is automatically submitted as the final answer (`uea_bedrock_agent.py:482-488`).
3. **Step limit:** a fixed timeout message is automatically submitted (`uea_bedrock_agent.py:523-527`).

This means “run submitted successfully” does not imply:

- the analysis completed;
- a non-empty or non-degenerate scientific answer exists;
- requested evidence was obtained;
- the answer contains conclusions;
- the model intentionally finalized.

Several stored runs contain only the roughly 80-byte step-limit message, yet have a successful `submit_answer` tool record.

### 5.4 Tool payload fragility

Tool execution does not consistently validate model-generated payloads before indexing them. For `run_command`, code accesses `payload["command"]` (`uea_bedrock_agent.py:314-315`). A malformed tool call can therefore raise `KeyError`.

The July IDR run failed exactly this way:

- run: `20260703_070321_idr-condensate-serine-charge_3f683aa3`
- failure at step 56;
- preceding model generation reached 8192 output tokens;
- `output.txt:29675` reports `UEA Bedrock agent failed: 'command'`;
- the runner then raises `CalledProcessError` around `output.txt:29697-29709`;
- no `final_answer.txt` exists;
- no `uea_bedrock_trace.json` was saved.

The trace is written only on the normal path after the loop (`uea_bedrock_agent.py:529-530`), so a late exception can discard the most useful diagnostic artifact.

### 5.5 Answer submission

`bioeval/bioeval/container_tools/submit_answer.py:49-66`:

- reads answer text from `--text` or `--file`;
- writes `results/final_answer.txt`;
- copies the supplied transcript to `results/transcript.txt`;
- records a tool-call event.

There is no:

- minimum content requirement;
- repetition/degeneracy check;
- schema for claims;
- required artifact manifest;
- evidence-link validation;
- check that the transcript corresponds to the answer;
- completion-state update.

The July butterfly run demonstrates the consequence: it wrote a 38,186-byte answer dominated by repeated “Let me now focus…” boilerplate after an 8192-token generation. The harness treated submission as successful.

---

## 6. Data request and grant pipeline

### 6.1 Hidden catalogs

Each complete problem has a host-only:

`problems_complete/<problem_id>/data_catalog.yaml`

Catalog entries include:

- internal ID;
- neutral description;
- kind (`raw`, `processed`, `derivable`, or `online`);
- grantability;
- local paths or online source;
- modalities;
- approximate byte size;
- evaluator notes and block reason.

`CatalogEntry.public_view()` in `schemas.py:55-62` removes paths and evaluator reasons. Grantable entries are exposed to the planner using order-dependent neutral names such as `dataset_001` (`schemas.py:78-98`).

Because public IDs depend on YAML order, inserting or reordering catalog entries changes the meaning of `dataset_001`. Historical logs can become hard to interpret across catalog revisions.

### 6.2 Planning cascade

The data-agent uses this fallback sequence (`bioeval/bioeval/data_agent.py:114-154`):

1. Bedrock planner;
2. opencode planner for compatible configurations;
3. direct OpenAI structured-output planner;
4. deterministic keyword selection.

The final fallback tokenizes the request and catalog text, counts token overlap, sorts by overlap, and prefers a local entry. It can silently change a run from semantic LLM planning to coarse keyword matching after an API failure.

This is operationally robust but experimentally problematic: two nominally equivalent runs may use different data-selection algorithms without being analyzed as separate conditions.

### 6.3 Specificity and grant caps

By default:

- `BIOEVAL_STRICT_DATA_REQUESTS=1`;
- `BIOEVAL_MAX_DATASET_GRANTS_PER_REQUEST=1`.

Broad inventory requests are denied. The UEA is expected to request a concrete measurement, organism/cohort, condition, modality, and scope. Online acquisition generally requires an explicit public source/accession request.

The single-dataset cap forces multi-modal tasks such as FORGE to obtain dependency, expression, and IC50 matrices through multiple successful requests. This makes request-planning skill and guard variance a large part of the score.

### 6.4 Staging and hidden filtering

`bioeval/bioeval/curation.py:819-976`:

1. rejects explicit deny plans and prohibited request language;
2. applies specificity checks;
3. caps grant instructions;
4. checks measurement-family compatibility;
5. resolves local or online assets;
6. optionally subsets RDS/tabular files based on request terms;
7. enforces byte limits;
8. runs the leak guard;
9. copies survivors under neutral grant paths;
10. reports `granted`, `partial`, or `denied`.

Observed logs frequently show a planner with `deny: false` and a selected instruction, followed by a denied grant from staging. This is expected given layered policy, but the resulting UEA outcome depends on multiple classifiers whose disagreement is not scored or normalized.

### 6.5 Leak guard

`bioeval/bioeval/guard.py:196-252` rejects:

- source-code and notebook extensions;
- serialized models;
- PDFs and many documentation formats;
- result-like filenames;
- archives containing code/repository hints;
- filenames or sampled contents matching hidden identifiers;
- spreadsheets with figure/statistic/result-like worksheet names.

Strengths:

- enforcement happens at the final data boundary;
- catalog mistakes do not automatically become UEA-visible;
- source code, models, papers, and obvious result artifacts are blocked;
- rejected staged files are removed before grant copy.

Limitations:

- large-file text inspection uses only head and tail samples, approximately 6 MB in total (`guard.py:67,108-116`);
- a marker located only in the middle of a very large file may evade scanning;
- result detection is heuristic;
- worksheet-name blocking can reject legitimate primary data merely because the authors organized it by figure;
- numeric answer leakage from summary tables can pass without paper identifiers.

### 6.6 Traffic guard and internet access

Search, literature, and page-fetch traffic is proxied through a traffic guard that can use an LLM and deterministic marker checks. It is intended to distinguish independent background literature from the held-out paper and derivatives.

Important properties:

- fail-closed behavior is configurable;
- decisions are cached in a process-global in-memory dictionary;
- cache entries have no documented TTL;
- Bedrock guard failures can block legitimate research;
- a commented-out host blocklist means hard egress denial is not enabled by default (`docker/compose.yaml:86-94`);
- the README acknowledges that a fully connected UEA may still discover a distinctive held-out task online (`README.md:289-292`).

Observed failures include:

- traffic-guard blocks on legitimate-looking organism/data requests;
- invalid traffic-guard decisions;
- DuckDuckGo timeouts;
- publisher/API 403, 404, and 429 responses;
- missing OpenAlex credentials.

These conditions directly change the scientific evidence available to a run.

---

## 7. How scoring actually works

### 7.1 Judge input

`bioeval/bioeval/judge.py:125-182` loads:

- hidden expected conclusions;
- hidden caveats;
- hidden judge rubric;
- title, DOI, and leak markers;
- UEA final answer;
- only the **last 40,000 characters** of the transcript.

The truncation is performed at `judge.py:150`:

```python
"uea_transcript_excerpt": transcript[-40_000:] if transcript else None
```

Any important data loading, cleaning, assumptions, or analysis performed earlier in a long transcript is invisible to the judge.

### 7.2 Per-conclusion labels

The judge prompt asks the LLM to assign:

- `matched`
- `partial`
- `missing`
- `wrong`

A conclusion should be “matched” only if:

- the final answer states it with correct directionality; and
- the transcript contains supporting analysis or evidence.

This is a sensible rubric conceptually, but evidence grounding is itself evaluated only by the judge LLM. The harness does not verify that cited files, commands, values, or transcript passages exist.

### 7.3 Suggested formula

The system prompt suggests:

```text
score ≈ (matched + 0.5 × partial) / number_of_expected_conclusions
```

with light adjustment for rigor and caveats.

It also suggests:

- pass: score ≥ 0.75
- borderline: score ≥ 0.50
- fail: score < 0.50

See `judge.py:49-51`.

### 7.4 What Python enforces

The LLM emits all of the following independently:

- overall score;
- verdict;
- per-conclusion rows;
- matched list;
- missing/wrong list;
- caveats addressed;
- leakage decision;
- rationale.

Pydantic validates types and score range, but Python does not:

- recompute score from per-conclusion statuses;
- derive verdict from score;
- ensure each expected conclusion appears exactly once;
- ensure duplicate summary lists agree with per-conclusion statuses;
- verify evidence against the transcript;
- verify quantitative values;
- compare generated outputs with hidden reference data.

The only substantive post-processing is:

```python
if result.leakage_suspected:
    result.score = min(result.score, 0.25)
    result.verdict = "fail"
```

See `judge.py:177-182`.

### 7.5 Leakage judgment

The judge is instructed to flag exact title, DOI, author names, repository names, or suspiciously exact paper-specific values. A leakage flag forces failure and caps score at 0.25.

This is not sufficient for data-mediated answer leakage. A grant can contain a summary table with the decisive biological relationship but no title, DOI, authors, or forbidden marker. Reading that table may earn a high score while `leakage_suspected` remains false.

### 7.6 No scientific metric recomputation

The evaluator does not programmatically recompute:

- survival curves or lifespan effects;
- Pearson correlation;
- average precision;
- AUROC;
- Markov-state model likelihoods;
- model-selection criteria;
- dependency/IC50 benefit scores;
- Spearman correlations or perturbation effects.

There are no hidden test scripts, metric adapters, artifact parsers, or tolerances tied to the five problem rubrics. The score is therefore a prose-recovery score, not a verified replication score.

### 7.7 Judge model dependence

The default judge is also Claude Sonnet 4.6, the same model family used by the default UEA and data planner. This may introduce correlated preferences and blind spots. There is no:

- independent judge family;
- multi-judge panel;
- judge calibration set;
- human adjudication protocol;
- judge disagreement measurement;
- repeated judge sampling.

Temperature 0 reduces sampling variance but does not make a hosted LLM deterministic across backend/model revisions.

---

## 8. Result files and run provenance

Documented artifacts include:

- `run_metadata.json`
- `TASK.md`
- `uea_workspace/`
- `data_grants/`
- `experiment_requests.jsonl`
- `results/terminal.typescript`
- `results/shell_commands.jsonl`
- `results/tool_calls.jsonl`
- `results/final_answer.txt`
- `results/transcript.txt`
- `uea_workspace/uea_bedrock_trace.json`
- `results/judge_result.json`
- `results/score_history.jsonl`
- component cost logs/JSON

This artifact design is one of the strongest parts of the system. In particular:

- `experiment_requests.jsonl` supports audit of feasibility/matcher/stager disagreements;
- `tool_calls.jsonl` distinguishes explicit submissions from tool errors;
- cost logs expose output-token saturation;
- grants can be inspected to determine whether conclusions were answer-encoded;
- judge history is append-only.

Current provenance weaknesses:

- run status is stale;
- model IDs are captured but hosted model revisions are not frozen;
- recent runs used a dirty git working tree;
- there is no immutable environment/container digest in the report;
- absent artifacts are not summarized as explicit failure states;
- there is no canonical run manifest saying which artifacts are required for validity.

---

## 9. What actually ran

### 9.1 Corpus inventory

The audited historical snapshot contained **44 retained runs with `run_metadata.json`** under `bioeval/runs/`, distributed as:

- butterfly: 25 timestamped attempts, plus a separate `smoke/` area without normal run metadata;
- F1-ATPase: 7;
- FORGE: 7;
- IDR: 5;

Approximately 30 runs contain submitted final answers. Only **6** contain `judge_result.json`.

The imbalance matters. A problem with 25 attempts and selective judging cannot be compared with a problem attempted once. There is no predefined rule for:

- number of trials;
- which trial counts;
- whether failed infrastructure runs are excluded;
- whether the best score, last score, or mean score is reported;
- when judging must occur.

### 9.2 The six judged runs

Stored judge outputs are:

- Butterfly, `20260624_185511_..._e52329a1`: 0.82, pass
- Butterfly, `20260625_181552_..._1cd8e998`: 0.75, pass
- Butterfly, `20260628_050202_..._2894288e`: 0.25, fail
- F1, `20260628_052654_..._01774114`: 0.15, fail
- FORGE, `20260628_055836_..._141bfde3`: 0.17, fail
- IDR, `20260628_061101_..._2ee70aa1`: 0.92, pass

The four June 28 judge calls were produced in a short coordinated manual window, roughly 06:34-06:36 UTC. Judging was post-hoc, not triggered automatically by run completion.

### 9.3 July 3 batch

`/home/mrsar/paper-invert/output.txt` records a sequential four-problem batch:

1. Butterfly:
   - run `20260703_054150_butterfly-longevity-pollen-feedi_3bce2faa`
   - 63 UEA calls
   - submitted a 38 KB degenerate repeated answer
   - one partial max-lifespan summary grant
   - no judge result

2. F1-ATPase:
   - run `20260703_062555_f1-atpase-markov-model_c27b289e`
   - 60 UEA calls
   - no useful problem-data grant
   - produced a literature synthesis rather than the required fitted model comparison
   - no judge result

3. FORGE:
   - run `20260703_064920_forge-cancer-drug-response_937e3ffc`
   - 48 UEA calls
   - obtained IC50/expression subsets
   - analyzed generic expression-to-response prediction
   - did not implement the required joint dependency/response FORGE construct
   - no judge result

4. IDR:
   - run `20260703_070321_idr-condensate-serine-charge_3f683aa3`
   - failed at step 56 with missing `command`
   - no final answer
   - no complete model trace
   - no judge result

All four recorded:

- git commit `031da037562d6149141bfd34bed693c04eebb2db`;
- `"dirty": true`;
- `"status": "initialized"`.

This batch cannot be summarized as a five-problem benchmark result. Four runs are unjudged and one is incomplete.

### 9.4 Butterfly score/grant association

The judged butterfly runs show a strong association between available evidence and judge score:

- 0.75/0.82 pass runs obtained broader survival/diet evidence;
- the 0.25 fail run obtained only a narrow Agraulis/Dryas table amid repeated denials;
- the July unjudged run obtained only max-lifespan summaries and degenerated.

This does not prove that grant breadth alone caused score differences, because the UEA trajectories also differ. It does establish that current scores confound:

- scientific reasoning;
- request wording;
- planner selection;
- traffic-guard outcomes;
- catalog availability;
- staging behavior.

### 9.5 IDR historical incompatibility

The 0.92 IDR pass used a single broad grant containing 22 spreadsheets, about 7 MB total. Worksheet names included figure/statistic-oriented labels such as:

- `Wilcoxon_Category_Stats(Fig5b)`
- `SRSF1_PhosphoMimic_vitro(Fig5g)`

The current leak guard's spreadsheet rule would reject such files because their worksheet names look like figure/result outputs (`guard.py:54-63,151-155`).

Consequences:

- the highest-scoring IDR run relied on data that current policy may no longer permit;
- old and new runs are not comparable;
- tightening leak policy changed the benchmark condition;
- the historical pass may reflect structured paper outputs more than independent rediscovery.

---

## 10. Per-problem audit

### 10.1 Butterfly longevity and pollen feeding

**Public task:** compare survival and physiology among neotropical butterflies and distinguish direct dietary effects from evolved lineage differences.

**Hidden targets:** longer lifespan in pollen-feeding Heliconius, roughly threefold extensions, diet effects that do not fully explain lineage differences, and slowed actuarial/physiological ageing including grip strength.

**Catalog intent:**

- individual survival RDS files;
- locomotor/grip datasets;
- supplementary CSVs;
- phylogeny;
- optional online figshare source.

**Observed local state:**

- catalog-referenced `.rds` primary files are absent;
- CSV summary tables and tree files are present;
- `nature-supplementary/` is absent;
- the manifest claims more assets than are currently on disk.

**Critical validity issue:** grantable supplementary/max-lifespan CSVs include columns such as:

- species;
- feeding habit;
- maximum lifespan;
- median lifespan.

One observed grant directly contains rows such as pollen-feeding Heliconius with maximum lifespans of 210-260 days. Another summary contains a 348-day maximum. These tables support major hidden conclusions without survival modeling.

**Evaluation consequence:** depending on the grant, the problem ranges from:

- impossible to fully answer because individual/diet/grip data are missing; to
- trivial lookup of a paper-derived summary.

There is no canonical evidence bundle or observational-analysis protocol, so runs do not evaluate the same task.

### 10.2 F1-ATPase Markov model

**Public task:** infer chemo-mechanical coupling from single-molecule, binding, and bulk kinetic constraints.

**Hidden targets:** a Markov model, comparison of four versus three beta conformations, bi-site/tri-site ATP dependence, and Brownian-ratchet rotation.

**Available data:**

- binding titration CSVs in the author repository tree;
- no complete neutral constraint bundle for rotation/step statistics;
- an online literature catalog entry with `online: null`;
- author model code is present host-side but correctly non-grantable.

**Validity problem:** the expected conclusion requires model-family construction and quantitative model selection, while the available grant path supplies only part of the necessary constraints. The July run therefore became a literature review and emphasized three-state knowledge rather than fitting and comparing the required models.

**Needed for validity:**

- a curated, non-answer-encoding table of all admissible experimental constraints;
- an explicit likelihood/objective;
- model comparison criteria;
- tolerances for the hidden expected behavior;
- artifact-based verification of fitted state models.

### 10.3 FORGE cancer drug response

**Public task:** predict targeted therapy response from molecular profiles, compare with simpler approaches, and assess generalization.

**Hidden targets:** joint dependency and drug-response modeling, expression layer, matrix factorization, a benefit score combining dependency and IC50, EGFR-erlotinib behavior, and external validation.

**Available data:**

- dependency matrix;
- expression matrix;
- IC50 matrix;
- Tahoe and PDX expression data;
- paper outputs and serialized FORGE models correctly marked non-grantable.

**Split issue:** author code contains a seeded 80/20 split (`seed=198716` in `repo/src/JointFORGE.py:198-220`), but the benchmark spec does not require that split or any equivalent canonical cell-line holdout.

**Evaluation risks:**

- full matrices can be granted with no enforced disjoint train/test protocol;
- different agents can choose incompatible splits;
- the single-dataset grant cap makes paired data acquisition fragile;
- large files interact with byte/subsetting logic;
- paper result files exist on the host and must remain reliably blocked.

The July run used expression and IC50 subsets but did not obtain/implement the required joint dependency model or benefit score. It evaluated generic drug-response prediction, not the target FORGE claim.

### 10.4 IDR condensate miscibility

**Public task:** determine sequence and perturbation determinants of condensate mixing versus demixing.

**Hidden targets:** serine/aromatic contributions to miscibility, charge-driven immiscibility, phosphorylation switching, and links to Pol II/transcription.

**Catalog intent:** grant Nature supplementary spreadsheets.

**Observed local state:** the catalog-referenced `nature-supplementary/*.xlsx` files are absent in the current problem directory.

**Guard conflict:** expected spreadsheet worksheet names contain figure identifiers and statistical-result terminology. Current `_xlsx_structure_leak` logic is designed to reject those names. Thus downloading the intended data may still leave the problem ungrantable.

**Historical inconsistency:** the 0.92 pass obtained a 22-file spreadsheet bundle under an earlier/effectively different policy. The July run obtained no grants and crashed.

This is not a stable evaluation condition.

## 11. Findings by severity

Severity definitions:

- **P0 Critical:** invalidates benchmark interpretation or makes the measured construct fundamentally different from the claimed one.
- **P1 High:** can materially alter pass/fail outcomes or prevent reproducible comparison.
- **P2 Medium:** significant robustness, auditability, or maintenance weakness.
- **P3 Low:** documentation or hygiene issue with limited direct score effect.

### P0-1: The benchmark score is only an LLM prose judgment

**Confidence:** very high  
**Evidence:** `bioeval/bioeval/judge.py:27-182`

No deterministic scientific metric or artifact checker exists. A score cannot substantiate paper replication.

### P0-2: Score arithmetic and verdict thresholds are not enforced

**Confidence:** very high  
**Evidence:** suggested rules at `judge.py:49-51`; only leakage post-processing at `judge.py:177-182`

The model can emit a score/verdict inconsistent with its own per-conclusion labels.

### P0-3: Data access confounds the scientific score

**Confidence:** very high  
**Evidence:** butterfly judged runs and July data-request histories

Grant breadth and traffic-guard outcomes strongly track whether conclusions are supportable.

### P0-4: Some grants directly encode expected conclusions

**Confidence:** very high  
**Evidence:** butterfly supplementary/max-lifespan grants; historical IDR spreadsheet bundle

The task can become reading paper-derived summaries rather than independently analyzing primary evidence.

### P0-5: Some expected tasks are structurally unattainable under current catalogs

**Confidence:** high  
**Evidence:** incomplete F1 constraints, absent IDR spreadsheets, missing butterfly RDS files

Failures cannot be attributed cleanly to agent ability.

### P0-6: Historical runs are not policy-comparable

**Confidence:** high  
**Evidence:** IDR pass bundle would be blocked by current spreadsheet guard; recent runs used dirty code

Policy and repository drift change the benchmark between runs.

### P1-1: Judging is manual and selective

**Confidence:** very high  
**Evidence:** runner contains no judge invocation; 45 runs with metadata versus 6 judge outputs

There is no unbiased rule selecting which attempts receive scores.

### P1-2: No repeated-trial or aggregation protocol exists

**Confidence:** very high

No pass@k, mean score, confidence interval, failure-rate accounting, or predefined trial count is implemented.

### P1-3: Transcript truncation can hide decisive evidence

**Confidence:** very high  
**Evidence:** `judge.py:150`

The judge sees only the last 40,000 characters.

### P1-4: Invalid submissions are accepted as completed

**Confidence:** very high  
**Evidence:** automatic no-tool submission, automatic step-limit submission, July butterfly repeated answer

Submission success is not evaluation validity.

### P1-5: Run lifecycle metadata is broken

**Confidence:** very high  
**Evidence:** `init_run.py:40`; all inspected statuses remain `initialized`

Automated analysis cannot reliably classify completed, failed, timed-out, crashed, or judged runs.

### P1-6: Tool payload errors can crash runs and lose traces

**Confidence:** very high  
**Evidence:** `uea_bedrock_agent.py:314-315,529-550`; July IDR failure

Schema validation and `finally`-based trace persistence are missing.

### P1-7: FORGE has no enforced holdout and latest run evaluated the wrong construct

**Confidence:** high  
**Evidence:** problem spec, author split code, July final answer/grants

Generic expression-to-IC50 prediction is not equivalent to joint FORGE modeling.

### P1-8: Traffic/staging guard failures produce false negatives

**Confidence:** high  
**Evidence:** planner-allow/stager-deny records, invalid guard decisions, legitimate requests blocked

Infrastructure policy is mixed into the capability score.

### P1-9: No Bedrock retry tolerance

**Confidence:** high  
**Evidence:** Bedrock client `total_max_attempts: 1`

Transient hosted-service failures can invalidate expensive runs.

### P1-10: No canonical numeric protocol for ML problems

**Confidence:** very high  
**Evidence:** the FORGE spec omits a binding split/seed/preprocessing definition

Even successful agents can report incomparable metrics.

### P2-1: UEA, planner, and judge share a model family

**Confidence:** high

Correlated preferences may inflate apparent agreement.

### P2-2: Fallback planner silently changes the experimental condition

**Confidence:** high  
**Evidence:** `data_agent.py:114-154`; keyword fallback in `curation.py:354-377`

Planner-mode provenance should be a first-class run field.

### P2-3: Public dataset IDs are YAML-order dependent

**Confidence:** very high  
**Evidence:** `schemas.py:78-98`

Catalog edits can reinterpret historical neutral IDs.

### P2-4: Traffic-guard cache is process-global and lacks TTL

**Confidence:** high  
**Evidence:** `search_proxy.py:171,518-520`

Long-lived container reuse can carry decisions across runs.

### P2-5: Leak scanning samples only parts of large files

**Confidence:** high  
**Evidence:** `guard.py:67,108-116`

Middle-only identifiers may evade content checks.

### P2-6: Online catalog pointers can be non-functional

**Confidence:** very high

Several `kind: online` entries have no usable `online` acquisition configuration.

### P2-7: Environment portability is weak

**Confidence:** high

Observed OpenAlex credential assumptions, missing ML dependencies, and hosted-service configuration make reproduction on another host difficult.

### P2-8: Model/environment provenance is insufficient

**Confidence:** high

Git SHA and model ID are recorded, but dirty diffs, container image digest, package lock, hosted model revision, planner mode, and network state are not frozen.

### P3-1: Documentation is inconsistent

**Confidence:** very high

Setup coverage and “complete” labels do not consistently match on-disk assets.

### P3-2: `problems_complete` overstates readiness

**Confidence:** very high

IDR primary files are absent and butterfly primary RDS assets are missing in the audited snapshot.

---

## 12. Bad patterns observed

The following patterns should not be used in benchmark reporting:

1. **Best-of-many without declaring selection.** Twenty-five butterfly attempts and three judged outcomes create substantial selection opportunity.
2. **Treating a submitted run as a completed scientific run.** Step-limit stubs and repeated text are accepted.
3. **Treating unjudged runs as failures or successes.** Four July answers have no score and IDR is incomplete.
4. **Mixing infrastructure failures with capability failures.** Search outages, API errors, guard invalidity, and tool payload crashes are not separated.
5. **Changing the protocol between runs.** Step limits changed from the documented 40 to 1000; guard rules evolved; recent runs used a dirty repository.
6. **Granting paper-shaped summary outputs.** This makes hidden claims directly readable.
7. **Scoring claims without checking artifacts.** The judge may accept prose describing an analysis even if the numerical result is not independently reproducible.
8. **No preregistered run inclusion rule.** There is no definition of which runs contribute to a benchmark number.
9. **No common per-problem protocol.** Different runs may receive different data, use different splits, and solve different variants.

---

## 13. What is sound and worth retaining

1. **Separation of public and hidden problem metadata.**
2. **Host-only data catalogs and planner logs.**
3. **Neutralized grant paths.**
4. **Layered staging plus leak guard.**
5. **Blocking of code, serialized models, papers, and obvious result artifacts.**
6. **Detailed tool, request, cost, and transcript artifacts.**
7. **Per-conclusion rubric structure.**
8. **Explicit leakage disqualification.**
9. **Strict-data-request philosophy.**
10. **Packaging each paper, repository, and data source as an inversion candidate.**

These are a strong foundation. The main issue is not the concept; it is that evaluation validity, task feasibility, and run governance have not caught up with the scaffold.

---

## 14. Defensible interpretation of current results

The six existing judge outputs support only these limited statements:

- Under particular historical grants and guard versions, two butterfly submissions and one IDR submission were judged by Sonnet 4.6 to recover enough hidden prose conclusions to pass.
- One other butterfly submission, one F1 submission, and one FORGE submission were judged to fail.
- The scores are sensitive to available data and are not normalized across grant conditions.
- The IDR pass relied on a broad spreadsheet bundle that appears incompatible with current guard policy.
- No valid aggregate performance estimate exists.
- The July five-problem batch has no judge outputs and includes invalid/incomplete runs.

They do **not** establish:

- a benchmark pass rate;
- repeatability;
- superiority over a baseline;
- reproduction of numerical paper results;
- robustness to grant variance;
- scientific discovery independent of paper-derived summary tables;
- performance on all five active problems.

---

## 15. Required remediation before benchmark claims

### Phase 1: Define valid runs

1. Add explicit lifecycle states:
   - initialized
   - running
   - submitted
   - invalid_submission
   - crashed
   - timed_out
   - judge_failed
   - judged
2. Persist traces in `finally`.
3. Validate all tool payloads against schemas.
4. Reject empty, repetitive, and step-limit boilerplate answers as invalid.
5. Automatically judge every valid submitted run or record a judge failure.
6. Record exact dirty diff or require a clean commit.
7. Record container digest, dependency lock, model revision if available, all relevant environment settings, and planner fallback mode.

### Phase 2: Make each problem feasible and fixed

1. Create an explicit readiness test for every catalog path.
2. Fail setup before a run if required assets are missing.
3. Remove paper-derived summary/figure outputs from the discovery evidence set.
4. Convert legitimate primary spreadsheets into neutral long-form tables if worksheet names would leak figure structure.
5. Define a canonical admissible evidence bundle or run a documented grant-condition ablation.
6. Supply F1 with a neutral complete experimental-constraint bundle.
7. Define mandatory FORGE holdouts and paired-matrix alignment.
8. Restore or re-download butterfly primary individual-level and physiology data.

### Phase 3: Make scoring checkable

1. Represent expected conclusions as structured claims with:
   - direction;
   - entity/condition;
   - expected statistic;
   - tolerance;
   - required evidence artifact.
2. Recompute numerical metrics from submitted artifacts.
3. Derive score and verdict in Python.
4. Use the LLM only for claim mapping and qualitative caveats.
5. Validate every evidence citation against the transcript and files.
6. Score the full event/command trace or a structured analysis manifest, not only the transcript tail.
7. Add an independent judge family or calibrated multi-judge/human adjudication for ambiguous prose.

### Phase 4: Establish experimental statistics

1. Predefine trial counts per problem/model.
2. Freeze UEA temperature and random-seed policy.
3. Define how infrastructure failures are retried or counted.
4. Report:
   - valid-run rate;
   - infrastructure-failure rate;
   - grant success rate;
   - per-problem score distribution;
   - confidence intervals;
   - pass@k where appropriate;
   - cost and token distribution.
5. Include fixed baselines:
   - no-data literature-only;
   - fixed-data bundle;
   - deterministic scripted analysis where possible;
   - human or expert reference.
6. Never report the best run without also reporting all attempts and the selection rule.

### Phase 5: Test the guards separately

The traffic guard and data grant policy need their own evaluation datasets:

- true held-out-paper requests;
- legitimate predecessor-literature requests;
- ambiguous related-work requests;
- raw-data requests;
- paper-derived result-data requests.

Measure false allow and false block rates separately. Do not infer guard quality from end-task score.

---

## 16. Recommended benchmark decomposition

The current single score should be decomposed into at least:

1. **Access score**
   - Were necessary admissible datasets requested and granted?
   - Were denials attributable to the UEA or guard failure?

2. **Execution score**
   - Did the run complete without infrastructure/tool failure?
   - Were required artifacts produced?

3. **Analysis score**
   - Do submitted artifacts reproduce hidden metrics within tolerance?

4. **Conclusion score**
   - Are hidden claims stated with correct direction and caveats?

5. **Leakage score**
   - Was any forbidden paper/code/result source accessed?

6. **Efficiency**
   - token cost;
   - wall time;
   - requests;
   - data bytes.

This decomposition would make it possible to distinguish “agent could not reason” from “the evaluator never provided the evidence.”

---

## 17. Suggested validity gates for publishing a score

A run should contribute to a benchmark result only if all are true:

- clean, frozen repository/environment;
- problem readiness test passes;
- required catalog assets exist;
- configured compute supports the requested task;
- run metadata reaches a terminal state;
- no unhandled infrastructure failure;
- non-degenerate final answer exists;
- complete trace and artifact manifest exist;
- judge ran successfully;
- deterministic score was reconciled from structured evidence;
- leakage checks passed;
- trial inclusion was preregistered.

A problem should contribute to an aggregate only if:

- at least one valid fixed-data or feasible open-world path exists;
- train/test rules are explicit where applicable;
- guard false-block behavior has been measured;
- multiple trials were run;
- uncertainty is reported.

The repository does not currently meet these gates.

---

## 18. Audit limitations

This audit is based on the repository snapshot and stored run artifacts present on 2026-07-15.

Limitations:

- hosted Bedrock backend revisions are not reconstructable from model IDs alone;
- absent `.env` values cannot be inferred beyond run metadata and command logs;
- some run directories are partial or smoke tests;
- no external paper-level scientific reanalysis was performed;
- data absence is a statement about this local snapshot, not necessarily upstream availability;
- causal attribution of score differences to grant breadth alone is not possible from observational run histories.

These limitations do not alter the central findings: scoring is LLM-only, judging is selective/manual, task conditions vary, several data paths are invalid or incomplete, and existing scores lack a reproducible statistical interpretation.

---

## 19. Final verdict

BioEval has a credible architectural idea and useful auditing infrastructure, but today it evaluates an unstable combination of:

- agent reasoning;
- data-request phrasing;
- planner behavior;
- guard behavior;
- data completeness;
- internet availability;
- runtime robustness;
- and LLM-judge preference.

It does not yet isolate scientific discovery ability, and it does not verify paper reproduction.

**Current status:** strong prototype, invalid as a headline benchmark.  
**Existing scores:** qualitative and historical, not aggregate evidence.  
**Highest priority:** fixed feasible problem protocols, removal of answer-encoding grants, deterministic artifact-based scoring, automatic lifecycle/judging, and repeated preregistered trials.

