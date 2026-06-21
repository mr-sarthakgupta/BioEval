# BioEval: Biology Paper-Inversion Scaffold

This is a minimal scaffold for evaluating whether an under-eval-agent (UEA) can
rediscover the core conclusions of a biology paper from an open-world problem
statement, internet access, analysis tools, and a guarded data-agent.

## Design

- The UEA starts in an empty `/workspace` with internet access and a fixed disk budget.
- The UEA does **not** receive the original paper, paper repository, answer key, or
  benchmark problem folder.
- The UEA calls `request_data "..."` to ask the data-agent for measurements or datasets,
  works in a recorded shell session, and calls `submit_answer` when it is done.
- The data-agent reasons with **opencode + GPT-5.5**. For each request it reads a hidden,
  host-only per-problem `data_catalog.yaml` (neutral dataset descriptions only) and
  produces a grant plan: which datasets to stage locally, which to subset, and which to
  fetch from public sources online.
- A **leak guard** scans everything before it reaches the UEA. It withholds source code,
  serialized models, manuscripts/PDFs, archives that contain code, and any file whose
  contents or name match hidden paper/repo identifiers. This is the real boundary: even
  if the catalog or agent misbehaves, the guard blocks the solution from leaking.
- Each evaluation run gets a unique directory under `runs/<problem_id>/<run_id>/`.
  Granted files are copied into that run's `data_grants` directory and mounted
  read-only at `/workspace/data` in the UEA container.
- Final answers are scored by `bioeval-judge` against hidden expected conclusions and
  the submitted analysis transcript, with per-conclusion grading. Suspected leakage is
  disqualifying.

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

Create a recorded run directory:

```bash
bioeval-init-run --problem-id "$BIOEVAL_PROBLEM_ID"
export BIOEVAL_RUN_ID=<printed run id>
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

The UEA also has SkyDiscover-style exploration tools, all recorded automatically:

- `read_file PATH [--line-start N --line-end M]`: read files under `/workspace`.
- `search PATTERN [--file-glob GLOB]`: regex search files under `/workspace`.
- `web_search QUERY`: search the web, with paper/repo/DOI/solution requests blocked.
- `research_papers search --query QUERY`: search scientific literature metadata for
  background methods and related datasets, with direct target-paper retrieval blocked.
- `fetch_webpage URL`: fetch allowed pages into `/workspace/reference`.
- `run_command COMMAND`: run constrained read-only commands in `/workspace`.

These tools are intended for open-world analysis while preserving the blind setup. They
cannot access host problem folders and should not be used to request the original paper,
DOI, repository, author code, solution, or expected conclusions.

The command prints a grant manifest with sandbox paths such as
`/workspace/data/<request_id>/dataset_001/file_001.csv`.

For very large datasets, ask for a subset, e.g.:

```bash
request_data "basal gene expression for a few hundred cancer cell lines, first 500 columns" --modality csv
```

Before requesting large files or generating outputs, the UEA should run:

```bash
check_space
```

Shell I/O, shell commands, and BioEval tool calls are recorded automatically. Use
`record_event` only for optional high-level annotations:

```bash
record_event --type note --text "Compared survival curves from the first granted table."
```

When finished, the UEA submits its conclusions:

```bash
submit_answer --text "Our conclusion is ..." --transcript analysis.log
# or: submit_answer --file answer.md --transcript analysis.log
```

## Judge A Run

`submit_answer` writes `final_answer.txt` and `transcript.txt` inside the active
run's `results/` directory on the host. Judge it with:

```bash
RUN_ROOT="runs/$BIOEVAL_PROBLEM_ID/$BIOEVAL_RUN_ID"
bioeval-judge \
  --problem-id "$BIOEVAL_PROBLEM_ID" \
  --run-id "$BIOEVAL_RUN_ID" \
  --final-answer-file "$RUN_ROOT/results/final_answer.txt" \
  --transcript-file "$RUN_ROOT/results/transcript.txt" \
  --output-file "$RUN_ROOT/results/judge_result.json" \
  --score-log "$RUN_ROOT/results/score_history.jsonl"
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

## Recorded Run Artifacts

Each run directory contains:

- `run_metadata.json`: problem id, run id, prompt, repo commit, resource/model env.
- `TASK.md`: the UEA-visible task text for the run.
- `uea_workspace/`: the UEA scratch workspace.
- `data_grants/`: neutral-path data grants mounted at `/workspace/data`.
- `data_requests.jsonl`: host-side data-agent request, planner, and grant log.
- `results/terminal.typescript`: full interactive terminal I/O transcript.
- `results/shell_commands.jsonl`: structured shell command ledger.
- `results/tool_calls.jsonl`: UEA-side BioEval tool calls and optional `record_event` entries.
- `results/final_answer.txt`: submitted answer.
- `results/transcript.txt`: submitted analysis transcript.
- `results/judge_result.json`: full judge result with metadata.
- `results/score_history.jsonl`: append-only judge score/feedback history.

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
  de-leaked prompts, neutral grant paths, optional egress blocklist, and leakage-fail
  judge policy mitigate but do not eliminate this. Hard network isolation is the
  production runner's responsibility.
