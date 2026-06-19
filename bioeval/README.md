# BioEval: Biology Paper-Inversion Scaffold

This is a minimal scaffold for evaluating whether an under-eval-agent (UEA) can
rediscover the core conclusions of a biology paper from an open-world problem
statement, internet access, analysis tools, and a guarded data-agent.

## Design

- The UEA starts in an empty `/workspace` with internet access and a fixed disk budget.
- The UEA does **not** receive the original paper, paper repository, answer key, or
  benchmark problem folder.
- The UEA calls `request_data "..."` to ask the data-agent for measurements or datasets,
  and `submit_answer` when it is done.
- The data-agent reasons with **opencode + GPT-5.5**. For each request it reads a hidden,
  host-only per-problem `data_catalog.yaml` (neutral dataset descriptions only) and
  produces a grant plan: which datasets to stage locally, which to subset, and which to
  fetch from public sources online.
- A **leak guard** scans everything before it reaches the UEA. It withholds source code,
  serialized models, manuscripts/PDFs, archives that contain code, and any file whose
  contents or name match hidden paper/repo identifiers. This is the real boundary: even
  if the catalog or agent misbehaves, the guard blocks the solution from leaking.
- Granted files are copied into `runs/data_grants` and mounted read-only at
  `/workspace/data` in the UEA container.
- Final answers are scored by `bioeval-judge` against hidden expected conclusions, with
  per-conclusion grading and a leakage-suspected flag.

```
request_data --> data-agent (opencode/GPT-5.5) --> grant plan
   --> stage local subset / fetch online --> leak guard --> /workspace/data (read-only)
```

### Anti-leak layers

1. The catalog only lists grantable raw/derivable/online data; author code, trained
   models, result/figure files, supplementary-information PDFs, and repository archives
   are marked non-grantable.
2. The data-agent only ever sees neutral descriptions (the public catalog view), never
   host paths, titles, DOIs, or block reasons. It emits a plan; the host executes it.
3. The leak guard re-checks every staged byte at the boundary.

## Install For Host Tools

```bash
cd /home/mrsar/paper-invert/bioeval
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env`. By default, both the data-agent and judge use
`gpt-5.5`.

## Run One Evaluation Sandbox

Pick a problem:

```bash
export BIOEVAL_PROBLEM_ID=s41467-026-73635-7_butterfly-longevity-pollen-feeding
```

Reset run state if you want a clean sandbox:

```bash
rm -rf runs/uea_workspace runs/data_grants
mkdir -p runs/uea_workspace runs/data_grants
```

Build and start the sandbox:

```bash
docker compose --env-file .env -f docker/compose.yaml up --build
```

In another terminal, enter the UEA container:

```bash
docker compose --env-file .env -f docker/compose.yaml exec uea bash
```

Print the UEA-visible task:

```bash
bioeval-print-prompt --problem-id "$BIOEVAL_PROBLEM_ID"
```

Inside the container, the UEA can request data:

```bash
request_data "survival data comparing pollen-feeding and non-pollen-feeding butterflies" --modality csv
```

The command prints a grant manifest with sandbox paths such as
`/workspace/data/<request_id>/supplementary_tables/Supplementary_Data_6.csv`.

For very large datasets, ask for a subset, e.g.:

```bash
request_data "basal gene expression for a few hundred cancer cell lines, first 500 columns" --modality csv
```

Before requesting large files or generating outputs, the UEA should run:

```bash
check_space
```

When finished, the UEA submits its conclusions:

```bash
submit_answer --text "Our conclusion is ..."   # or: submit_answer --file answer.md
```

## Judge A Run

`submit_answer` writes `runs/results/final_answer.txt` (and optionally
`runs/results/transcript.txt`) on the host. Judge it with:

```bash
bioeval-judge \
  --problem-id "$BIOEVAL_PROBLEM_ID" \
  --final-answer-file runs/results/final_answer.txt \
  --transcript-file runs/results/transcript.txt   # optional
```

The judge returns JSON:

```json
{
  "score": 0.0,
  "verdict": "fail",
  "per_conclusion": [{"conclusion": "...", "status": "missing", "evidence": "..."}],
  "matched_conclusions": [],
  "missing_or_wrong": [],
  "caveats_addressed": [],
  "leakage_suspected": false,
  "leakage_rationale": "",
  "rationale": "..."
}
```

## Current Problems

- `s41467-026-73844-0_f1-atpase-markov-model`
- `s41467-026-73635-7_butterfly-longevity-pollen-feeding`
- `s41467-026-73977-2_forge-cancer-drug-response`
- `s41589-026-02251-9_idr-condensate-serine-charge`

Problem specs live in `bioeval/problem_specs`. The UEA-visible prompt is
`sandbox_prompt`; `expected_conclusions`, `expected_caveats`, `judge_rubric`, and
`leak_markers` are hidden benchmark metadata. The grantable data per problem is defined
by the hidden `data_catalog.yaml` inside each problem folder.

## Notes And Guardrails

- The data-agent uses opencode + GPT-5.5 to choose datasets. If opencode is unavailable,
  it falls back to a direct OpenAI structured-output call, then to deterministic keyword
  matching over the catalog, so the pipeline always runs.
- Online acquisition is real (Zenodo / figshare / direct URL via `bioeval/providers.py`).
  Everything fetched still passes through the leak guard.
- The leak guard (`bioeval/guard.py`) is the enforced boundary. To add a new problem,
  write its `data_catalog.yaml` and a problem spec; mark code/models/results/PDFs/archives
  non-grantable and set `leak_markers` (title, authors, repo) so the guard can catch them.
- Resource limits: `mem_limit`, `cpus`, and `pids_limit` are enforced by Docker.
  `storage_opt.size` is a best-effort disk quota (needs a quota-capable storage driver);
  `check_space` enforces `BIOEVAL_DISK_BUDGET_GB` cooperatively and exits non-zero when
  over budget. An optional `extra_hosts` blocklist in `docker/compose.yaml` can blackhole
  the hosts that serve the original paper/repo.
- A fully internet-connected UEA could still search for a distinctive problem online; the
  de-leaked prompts, the optional egress blocklist, and the judge's `leakage_suspected`
  flag mitigate but do not eliminate this. Hard network isolation is the production
  runner's responsibility.
